import os
import re
import typing
import datetime
import pathlib
import functools
import contextvars
import contextlib
import json

from . import errors
from . import ref_base
from . import artifact_base
from . import artifact_mem
from . import artifact_fs
from . import artifact_local
from . import artifact_wandb
from . import weave_types as types
from . import mappers_python
from . import box
from . import errors
from . import graph
from . import graph_client_context
from . import timestamp

Ref = ref_base.Ref

if typing.TYPE_CHECKING:
    from weave.wandb_interface.wandb_lite_run import InMemoryLazyLiteRun


def split_path_dotfile(path, dotfile_name):
    while path != "/":
        path, tail = os.path.split(path)
        if os.path.exists(os.path.join(path, dotfile_name)):
            return path, tail
    raise FileNotFoundError


def _get_name(wb_type: types.Type, obj: typing.Any) -> str:
    if getattr(obj, "name", None) != None:
        return obj.name
    return wb_type.name
    # This tries to figure out which variable references obj.
    # But it is slow when there are a lot of references. If we want to do
    # something like this, we'll need to do it somewhere closer to user
    # interaction.
    # obj_names = util.find_names(obj)
    # return f"{wb_type.name}-{obj_names[-1]}"


def _get_weave_type_with_refs(obj: typing.Any):
    try:
        return types.type_of_with_refs(obj)
    except errors.WeaveTypeError as e:
        raise errors.WeaveSerializeError(
            "weave type error during serialization for object: %s. %s"
            % (obj, str(e.args))
        )


def _ensure_object_components_are_published(
    obj: typing.Any, wb_type: types.Type, artifact: artifact_wandb.WandbArtifact
):
    from weave.mappers_publisher import map_to_python_remote

    mapper = map_to_python_remote(wb_type, artifact)
    return mapper.apply(obj)


def _assert_valid_name_part(part: typing.Optional[str] = None):
    if part is None:
        return
    if not re.match(r"^[a-zA-Z0-9_\-]+$", part):
        raise ValueError(
            "Invalid name part %s. Must be alphanumeric, dashes, or underscores." % part
        )


def _assert_valid_entity_name(part: typing.Optional[str] = None):
    if part is None:
        return
    if not re.match(r"^[a-z0-9_\-]+$", part):
        raise ValueError(
            "Invalid entity name %s. Must be lowercase, digits, dashes, or underscores."
            % part
        )


def _assert_valid_project_name(part: typing.Optional[str] = None):
    if part is None:
        return
    if len(part) > 128:
        raise ValueError("Invalid project name %s. Must be <= 128 characters." % part)
    if re.match(r"[\\#?%:]", part):
        raise ValueError(
            "Invalid project name %s. Can not contain \\, #, ?, %%, or :" % part
        )


def _assert_valid_artifact_name(part: typing.Optional[str] = None):
    if part is None:
        return
    if len(part) > 128:
        raise ValueError("Invalid artifact name %s. Must be <= 128 characters." % part)
    if not re.match(r"^[a-zA-Z0-9_\-.]+$", part):  # from W&B Artifacts
        raise ValueError(
            "Invalid artifact name %s. Must be alphanumeric, periods, dashes, or underscores."
            % part
        )


class PublishTargetProject(typing.TypedDict):
    # TODO: should include entity_name as well, but we defalt that right now...
    # entity_name: str
    project_name: str


_pubish_target_project: contextvars.ContextVar[
    typing.Optional[typing.Optional[PublishTargetProject]]
] = contextvars.ContextVar("publish_target_project", default=None)


@contextlib.contextmanager
def publish_target_project(project: PublishTargetProject):
    token = _pubish_target_project.set(project)
    yield
    _pubish_target_project.reset(token)


def get_publish_target_project() -> typing.Optional[PublishTargetProject]:
    return _pubish_target_project.get()


# Keep a cache of published local ref -> wandb ref. This is used to ensure
# we publish any needed op defs at the beginning of graph execution one time,
# to avoid parallel publishing them many times later in mapped operations.
PUBLISH_CACHE_BY_LOCAL_ART: dict[
    artifact_local.LocalArtifactRef, artifact_wandb.WandbArtifactRef
] = {}


def _direct_publish(
    obj: typing.Any,
    name: typing.Optional[str] = None,
    wb_project_name: typing.Optional[str] = None,
    wb_artifact_type_name: typing.Optional[str] = None,
    wb_entity_name: typing.Optional[str] = None,
    branch_name: typing.Optional[str] = None,
    metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
    assume_weave_type: typing.Optional[types.Type] = None,
    *,
    _lite_run: typing.Optional["InMemoryLazyLiteRun"] = None,
    _merge: typing.Optional[bool] = False,
) -> artifact_wandb.WandbArtifactRef:
    _orig_obj = obj
    _orig_ref = _get_ref(obj)
    if isinstance(_orig_ref, artifact_wandb.WandbArtifactRef):
        return _orig_ref
    if isinstance(_orig_ref, artifact_local.LocalArtifactRef):
        res = PUBLISH_CACHE_BY_LOCAL_ART.get(_orig_ref)
        if res is not None:
            ref_base._put_ref(obj, res)
            return res

    weave_type = assume_weave_type or _get_weave_type_with_refs(obj)

    target_project_from_context = get_publish_target_project()
    if target_project_from_context is not None:
        wb_project_name = target_project_from_context["project_name"]
    else:
        wb_project_name = wb_project_name or artifact_wandb.DEFAULT_WEAVE_OBJ_PROJECT
    name = name or _get_name(weave_type, obj)
    wb_artifact_type_name = wb_artifact_type_name or weave_type.root_type_class().name

    _assert_valid_artifact_name(name)
    _assert_valid_project_name(wb_project_name)
    _assert_valid_name_part(wb_artifact_type_name)
    _assert_valid_name_part(branch_name)
    _assert_valid_entity_name(wb_entity_name)
    # Validate entity name once we have them

    obj = box.box(obj)
    artifact = artifact_wandb.WandbArtifact("", name, type=wb_artifact_type_name)
    artifact.metadata.update(metadata or {})

    # Use context to ensure any recursively published objects go to the same project
    with publish_target_project({"project_name": wb_project_name}):
        obj = _ensure_object_components_are_published(obj, weave_type, artifact)
    artifact_fs.update_weave_meta(weave_type, artifact)
    ref = artifact.set("obj", weave_type, obj)
    if not isinstance(ref, artifact_wandb.WandbArtifactRef):
        raise errors.WeaveSerializeError(
            "Expected a WandbArtifactRef, got %s" % type(ref)
        )

    # Only save if we have a ref into the artifact we created above. Otherwise
    # nothing new was created, so just return the existing ref.
    if ref.artifact == artifact:
        artifact.save(
            project=wb_project_name,
            entity_name=wb_entity_name,
            branch=branch_name,
            artifact_collection_exists=bool(_merge),
            _lite_run=_lite_run,
        )

    if isinstance(_orig_ref, artifact_local.LocalArtifactRef):
        PUBLISH_CACHE_BY_LOCAL_ART[_orig_ref] = ref

    ref_base._put_ref(obj, ref)
    ref_base._put_ref(_orig_obj, ref)

    return ref


def direct_save(
    obj: typing.Any,
    name: typing.Optional[str] = None,
    branch_name: typing.Optional[str] = None,
    source_branch_name: typing.Optional[str] = None,
    assume_weave_type: typing.Optional[types.Type] = None,
    artifact: typing.Optional[artifact_local.LocalArtifact] = None,
) -> artifact_local.LocalArtifactRef:
    weave_type = assume_weave_type or _get_weave_type_with_refs(obj)
    name = name or _get_name(weave_type, obj)

    _assert_valid_name_part(name)
    _assert_valid_name_part(branch_name)
    _assert_valid_name_part(source_branch_name)

    obj = box.box(obj)
    if artifact is None:
        # Using `version=source_branch_name` feels too magical. Would be better
        # to have a classmethod on LocalArtifact that takes a branch name and
        # returns an artifact with that branch name. This also precludes
        # directly saving an artifact with a branchpoint that is not local
        artifact = artifact_local.LocalArtifact(name, version=source_branch_name)
        artifact_fs.update_weave_meta(weave_type, artifact)
    ref = artifact.set("obj", weave_type, obj)

    # Only save if we have a ref into the artifact we created above. Otherwise
    #     nothing new was created, so just return the existing ref.
    if ref.artifact == artifact:
        artifact.save(branch=branch_name)

    return ref  # type: ignore


def publish(obj, name=None, type=None):
    # We would probably refactor this method to be more like _direct_publish. This effectively
    # just a wrapper that let's the user specify project name with a slash.
    # TODO: should we only expose save for our API with a "remote" flag or something
    project_name = None
    if name is not None and "/" in name:
        project_name, name = name.split("/")

    return _direct_publish(
        obj,
        name=name,
        wb_project_name=project_name,
        assume_weave_type=type,
    )


def save(
    obj,
    name=None,
    type=None,
    artifact=None,
    branch=None,
) -> artifact_local.LocalArtifactRef:
    # We would probably refactor this method to be more like direct_save. This effectively
    # just a wrapper that let's the user specify source_branch name with a slash.
    source_branch = None
    if name is not None and ":" in name:
        name, source_branch = name.split(":", 1)

    return direct_save(
        obj=obj,
        name=name,
        branch_name=branch,
        source_branch_name=source_branch,
        assume_weave_type=type,
        artifact=artifact,
    )


def get(uri_s: typing.Union[str, ref_base.Ref]) -> typing.Any:
    if isinstance(uri_s, ref_base.Ref):
        return uri_s.get()
    return ref_base.Ref.from_str(uri_s).get()


get_local_version_ref = artifact_local.get_local_version_ref
get_local_version = artifact_local.get_local_version


def deref(ref):
    if isinstance(ref, ref_base.Ref):
        return ref.get()
    return ref


def _get_ref(obj: typing.Any) -> typing.Optional[ref_base.Ref]:
    if isinstance(obj, ref_base.Ref):
        return obj
    return ref_base.get_ref(obj)


def clear_ref(obj):
    ref_base.clear_ref(obj)


get_ref = _get_ref


# Return all local artifacts.
# Warning: may iterate a lot of the filesystem!
def local_artifacts() -> typing.List[artifact_local.LocalArtifact]:
    result = []
    obj_paths = sorted(
        pathlib.Path(artifact_local.local_artifact_dir()).iterdir(),
        key=os.path.getctime,
    )
    for art_path in obj_paths:
        if os.path.basename(art_path) != "tmp":
            result.append(artifact_local.LocalArtifact(art_path.name, None))
    return result


def all_objects():
    result = []
    obj_paths = sorted(
        pathlib.Path(artifact_local.local_artifact_dir()).iterdir(),
        key=os.path.getctime,
    )
    for art_path in obj_paths:
        ref = artifact_local.get_local_version_ref(art_path.name, "latest")
        if ref is not None:
            result.append((ref.created_at, ref))
    return [r[1] for r in sorted(result)]


def objects(
    of_type: types.Type, alias: str = "latest"
) -> typing.List[artifact_local.LocalArtifactRef]:
    result = []
    for art_name in os.listdir(artifact_local.local_artifact_dir()):
        try:
            ref = artifact_local.get_local_version_ref(art_name, alias)
            if ref is not None:
                if of_type.assign_type(ref.type):
                    # TODO: Why did I have this here?
                    # obj = ref.get()
                    # if isinstance(ref.type, types.RunType) and obj.op_name == "op-objects":
                    #     continue
                    result.append((ref.artifact.created_at, ref))
        except errors.WeaveSerializeError:
            # This happens because we may not have loaded ecosystem stuff that we need
            # to deserialize
            continue
    # Sorted by created_at
    return [r[1] for r in sorted(result)]


def recursively_unwrap_arrow(obj):
    if getattr(obj, "to_pylist_notags", None):
        return obj.to_pylist_notags()
    if getattr(obj, "as_py", None):
        return obj.as_py()
    if isinstance(obj, graph.Node):
        return obj
    if isinstance(obj, dict):
        return {k: recursively_unwrap_arrow(v) for (k, v) in obj.items()}
    elif isinstance(obj, list):
        return [recursively_unwrap_arrow(item) for item in obj]
    return obj


def _default_ref_persister_artifact(
    type: types.Type, refs: typing.Iterable[artifact_base.ArtifactRef]
) -> artifact_base.Artifact:
    fs_art = artifact_local.LocalArtifact(type.name, "latest")
    # Save all the reffed objects into the new artifact.
    for mem_ref in refs:
        if mem_ref.path is not None and mem_ref._type is not None:
            fs_art.set(mem_ref.path, mem_ref._type, mem_ref._obj)
    fs_art.save()
    return fs_art


def to_python(
    obj: typing.Any,
    wb_type: typing.Optional[types.Type] = None,
    ref_persister: typing.Callable[
        [types.Type, typing.Iterable[artifact_base.ArtifactRef]], artifact_base.Artifact
    ] = _default_ref_persister_artifact,
) -> dict:
    if wb_type is None:
        wb_type = types.type_of_with_refs(obj)

    # First map the object using a MemArtifact to capture any custom object refs.
    art = artifact_mem.MemArtifact()
    mapper = mappers_python.map_to_python(wb_type, art)
    val = mapper.apply(obj)

    if art.ref_count() > 0:
        # There are custom objects, create a local artifact to persist them.
        fs_art = ref_persister(wb_type, art.refs())
        # now map the original object again. Because there are now existing refs
        # to the local artifact for any custom objects, this new value will contain
        # those existing refs as absolute refs. We provide None for artifact because
        # it should not be used in this pass.
        # TODO: actually had to add artifact here to get HF/Bertviz caching
        # to work. Why?
        mapper = mappers_python.map_to_python(wb_type, fs_art)  # type: ignore
        val = mapper.apply(obj)
    # TODO: this should be a ConstNode!
    return {"_type": wb_type.to_dict(), "_val": val}


def to_safe_const(obj):
    wb_type = types.TypeRegistry.type_of(obj)
    mapper = mappers_python.map_to_python(wb_type, artifact_mem.MemArtifact())
    val = mapper.apply(obj)
    return graph.ConstNode(wb_type, val)


def from_python(obj: dict, wb_type: typing.Optional[types.Type] = None) -> typing.Any:
    if wb_type is None:
        wb_type = types.TypeRegistry.type_from_dict(obj["_type"])
    mapper = mappers_python.map_from_python(wb_type, None)  # type: ignore
    res = mapper.apply(obj["_val"])
    return res


def to_json_with_refs(
    obj: typing.Any,
    artifact: artifact_base.Artifact,
    path: typing.Optional[list[str]] = None,
    wb_type: typing.Optional[types.Type] = None,
):
    """Convert an object to a JSON-serializable object, with refs to any custom objects.

    Contains business logic:
      - OpDef are always saved as top-level artifacts.
      - All other custom objects are saved as refs within the provided artifact
        if there is not are a ref available for them.
    """

    # This is newer than to_python, save and publish above, and doesn't use the "mapper"
    # pattern, which is overkill. Much better to just write a simple function like this.
    from . import op_def

    if wb_type is None:
        wb_type = types.TypeRegistry.type_of(obj)
    if path is None:
        path = []
    if isinstance(wb_type, (types.Number, types.String, types.NoneType, types.Boolean)):
        return obj
    elif isinstance(wb_type, types.UnknownType):
        raise errors.WeaveTypeError(f"Can't serialize {obj}. Type is UnknownType.")
    elif isinstance(wb_type, types.TypedDict):
        if not isinstance(obj, dict):
            raise ValueError("Expected dict for TypedDict, got %s" % type(obj).__name__)
        return {
            k: to_json_with_refs(
                v, artifact, path + [k], wb_type=wb_type.property_types[k]
            )
            for (k, v) in obj.items()
        }
    elif isinstance(wb_type, types.List):
        if not isinstance(obj, list):
            raise ValueError("Expected list for List, got %s" % type(obj).__name__)
        return [
            to_json_with_refs(v, artifact, path + [str(i)], wb_type=wb_type.object_type)
            for i, v in enumerate(obj)
        ]
    elif isinstance(obj, op_def.OpDef):
        try:
            gc = graph_client_context.require_graph_client()
        except errors.WeaveInitError:
            raise errors.WeaveSerializeError(
                "Can't serialize OpDef with a client initialization"
            )
        return gc.save_object(obj, obj.name, "latest")
    else:
        res = artifact.set("/".join(path), wb_type, obj)
        if res.artifact == artifact:
            res.serialize_as_path_ref = True
        return res


def make_js_serializer():
    artifact = artifact_mem.MemArtifact()
    return functools.partial(to_weavejs, artifact=artifact)


def convert_timestamps_to_epoch_ms(obj: typing.Any) -> typing.Any:
    if isinstance(obj, list):
        return [convert_timestamps_to_epoch_ms(o) for o in obj]
    if isinstance(obj, dict):
        return {k: convert_timestamps_to_epoch_ms(v) for k, v in obj.items()}
    if isinstance(obj, datetime.datetime):
        return timestamp.python_datetime_to_ms(obj)
    return obj


def to_weavejs(obj, artifact: typing.Optional[artifact_base.Artifact] = None):
    from .arrow import list_ as arrow_list

    obj = box.unbox(obj)
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, dict):
        return {k: to_weavejs(v, artifact=artifact) for (k, v) in obj.items()}
    elif isinstance(obj, list):
        return [to_weavejs(item, artifact=artifact) for item in obj]
    elif isinstance(obj, arrow_list.ArrowWeaveList):
        return arrow_list.convert_arrow_timestamp_to_epoch_ms(obj).to_pylist_notags()

    wb_type = types.TypeRegistry.type_of(obj)

    if artifact is None:
        artifact = artifact_mem.MemArtifact()

    mapper = mappers_python.map_to_python(
        wb_type, artifact, mapper_options={"use_stable_refs": False}
    )
    return mapper.apply(obj)


def artifact_path_ref(artifact_path: str) -> artifact_base.ArtifactRef:
    """Return a reference to an object in the current artifact based on its path.

    This is only callable during artifact loading, and should not generally be
    called by user code.
    """
    loading_artifact = artifact_fs.get_loading_artifact()
    if loading_artifact is None:
        raise errors.WeaveSerializeError(
            "artifact_path_ref can only be used while loading an artifact."
        )

    return loading_artifact.ref_from_local_str(artifact_path)
