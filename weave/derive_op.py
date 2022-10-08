import copy
import inspect
import typing

from . import weave_types as types
from . import op_args
from . import registry_mem
from . import op_def
from . import errors
from . import graph
from . import box


class DeriveOpHandler:
    """
    Subclassing this class will add a new type of derived op to the Weave1 system
    """

    handler_id: typing.ClassVar[str]

    @staticmethod
    def derived_name(name: str) -> str:
        raise NotImplementedError()

    @staticmethod
    def should_derive_op(orig_op: op_def.OpDef) -> bool:
        raise NotImplementedError()

    @staticmethod
    def make_derived_op(orig_op: op_def.OpDef) -> op_def.OpDef:
        raise NotImplementedError()

    @staticmethod
    def handle_class_decorator_update(
        derived_op: op_def.OpDef,
        base_weave_type: type[types.Type],
        orig_op_new_name: str,
    ):
        raise NotImplementedError()


# These are a list of type names that should not be mapped
disallow_mapping_type_name_list = [
    "list",
    "wbtable",
    "ndarray",
    "ArrowArray",
    "ArrowTable",
    "ArrowTableGroupBy",
    "ArrowWeaveList",
    "dataframe",
    "sqltable",
    "projectArtifactVersions",
    "runs",
    "artifacts",
    "projectArtifactTypes",
    "invalid",
    "unknown",
    "none",
    "any",
    "groupresult",
    "table",
    "dataframeTable",
    "ArrowTableGroupResult",
    "ArrowWeaveList",
]


class MappedDeriveOpHandler(DeriveOpHandler):
    handler_id = "mapped"

    @staticmethod
    def derived_name(name: str) -> str:
        if "-" not in name:
            return f"mapped-{name}"
        else:
            return f"mapped_{name}"

    @staticmethod
    def should_derive_op(orig_op: op_def.OpDef) -> bool:
        """Returns True if the op should be mapped to a list of inputs."""
        named_args = orig_op.input_type.named_args()

        # The argument list must be named AND have at least 1 argument.
        if len(named_args) == 0:
            return False

        first_arg = named_args[0]

        # Enforce the disallow list
        if first_arg.type.class_type_name() in disallow_mapping_type_name_list:
            return False

        # Here, we check if the first_arg is unknown. If it is, then we cannot tell
        # if it is supposed to be mapped.
        if first_arg.type == types.UnknownType():
            return False

        # If the first argument can be assigned to a list<any>, then we should not map it -
        # it will create unresolvable ambiguity between the current op and the mapped.
        if types.List(types.Any()).assign_type(first_arg.type):
            return False

        # If the first argument can be assigned a list of the first argument, then we should not map -
        # this too will create unresolvable ambiguity.
        if first_arg.type.assign_type(types.List(first_arg.type)):
            return False

        return True

    @staticmethod
    def make_derived_op(orig_op: op_def.OpDef) -> op_def.OpDef:
        mapped_op_name = MappedDeriveOpHandler.derived_name(
            orig_op.name
        )  # TODO: doesn't handle fqn
        named_args = orig_op.input_type.named_args()

        if len(named_args) == 0 or not isinstance(
            orig_op.input_type, op_args.OpNamedArgs
        ):
            raise errors.WeaveInternalError(
                f"Cannot make mapped op for op {orig_op.name} with no first named argument."
            )
        first_arg = named_args[0]
        mapped_param_name = first_arg.name

        output_type: typing.Union[types.Type, typing.Callable]
        if not callable(orig_op.output_type):
            output_type = types.List(types.optional(orig_op.output_type))
        else:

            def make_output_type(input_types):
                replacement = input_types[mapped_param_name].object_type

                # This is a special circumstance (aka "God Mode") where we are
                # inferring when an external caller is trying to weaveify this
                # function. In this specific case, we need to manually construct the
                # output_type. The main reason for this is that `merge` is not yet
                # implemented as a core op that looks the same in python and weave.
                # Therefore the `inner_input_types[mapped_param_name] = replacement`
                # line below will not work. This is a temporary fix until we can
                # implement `merge` as a core op.
                currently_weavifying = isinstance(
                    input_types, graph.Node
                ) and types.TypedDict({}).assign_type(input_types.type)
                if currently_weavifying:
                    op_dict = registry_mem.memory_registry.get_op("dict")
                    op_dict.instance = None
                    inner_input_types = input_types.merge(
                        op_dict(**{mapped_param_name: replacement})
                    )
                    try:
                        inner_res = orig_op.output_type(inner_input_types)
                    except errors.WeaveExpectedConstError as e:
                        raise errors.WeaveMakeFunctionError(
                            "function body expected const node."
                        )
                    if not isinstance(inner_res, graph.Node):
                        raise errors.WeaveMakeFunctionError(
                            "output_type function must return a node."
                        )
                    return types.List.make({"object_type": inner_res})

                inner_input_types = copy.copy(input_types)
                inner_input_types[mapped_param_name] = replacement
                return types.List(
                    types.optional(orig_op.output_type(inner_input_types))
                )

            output_type = make_output_type

        def resolve(**inputs):
            new_inputs = copy.copy(inputs)
            list_ = new_inputs.pop(mapped_param_name)
            # TODO: use the vectorization described here:
            # https://paper.dropbox.com/doc/Weave-Python-Weave0-Op-compatibility-workstream-kJ3XSDdgR96XwKPapHwPD
            return [
                orig_op.resolve_fn(x, **new_inputs)
                if not (x is None or isinstance(x, box.BoxedNone))
                else None
                for x in list_
            ]

        # Use the function signature of the original op to compute the signature
        # of the lazy call
        resolve.sig = inspect.signature(orig_op.resolve_fn)  # type: ignore
        input_type = copy.copy(orig_op.input_type.arg_types)
        input_type[mapped_param_name] = types.List(first_arg.type)
        new_op = op_def.OpDef(
            mapped_op_name, op_args.OpNamedArgs(input_type), output_type, resolve
        )
        op_version = registry_mem.memory_registry.register_op(new_op)

        return op_version

    @staticmethod
    def handle_class_decorator_update(
        derived_op: op_def.OpDef,
        base_weave_type: type[types.Type],
        orig_op_new_name: str,
    ):
        named_args = derived_op.input_type.named_args()
        if len(named_args) == 0 or not isinstance(
            derived_op.input_type, op_args.OpNamedArgs
        ):
            raise errors.WeaveDefinitionError(
                f"Expected mapped op {derived_op.name} to have named first argument."
            )
        first_arg = named_args[0]
        # Check to see if the first argument is a list of UnknownType. This is how
        # we know that the type is expected to be the class type
        first_arg_is_cls = first_arg.type == types.List(types.UnknownType())
        if first_arg_is_cls:
            derived_op.input_type.arg_types[first_arg.name] = types.List(
                base_weave_type()
            )
        registry_mem.memory_registry.rename_op(
            derived_op.name, MappedDeriveOpHandler.derived_name(orig_op_new_name)
        )


def handler_for_id(handler_id: str) -> type[DeriveOpHandler]:
    for handler in DeriveOpHandler.__subclasses__():
        if handler.handler_id == handler_id:
            return handler
    raise errors.WeaveInternalError(f"Unknown derive op handler {handler_id}")


def derive_ops(op: op_def.OpDef):
    for handler in DeriveOpHandler.__subclasses__():
        if handler.should_derive_op(op) and handler.handler_id not in op.derived_ops:
            op.derived_ops[handler.handler_id] = handler.make_derived_op(op)
