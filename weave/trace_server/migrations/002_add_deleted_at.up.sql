ALTER TABLE object_versions
    ADD COLUMN deleted_at Nullable(DateTime64(3)) DEFAULT NULL;

CREATE OR REPLACE VIEW object_versions_deduped as
    SELECT project_id,
        object_id,
        created_at,
        deleted_at,
        kind,
        base_object_class,
        refs,
        val_dump,
        digest,
        if (kind = 'op', 1, 0) AS is_op,
        row_number() OVER (
            PARTITION BY project_id,
            kind,
            object_id
            ORDER BY created_at ASC
        ) AS _version_index_plus_1,
        _version_index_plus_1 - 1 AS version_index,
        count(*) OVER (PARTITION BY project_id, kind, object_id) as version_count,
        if(_version_index_plus_1 = version_count, 1, 0) AS is_latest
    FROM (
            SELECT *,
                row_number() OVER (
                    PARTITION BY project_id,
                    kind,
                    object_id,
                    digest
                    ORDER BY created_at ASC
                ) AS rn
            FROM object_versions
        )
    WHERE rn = 1 WINDOW w AS (
            PARTITION BY project_id,
            kind,
            object_id
            ORDER BY created_at ASC
        )
    ORDER BY project_id,
        kind,
        object_id,
        created_at;

ALTER TABLE call_parts
    ADD COLUMN deleted_at Nullable(DateTime64(3)) DEFAULT NULL;

ALTER TABLE calls_merged
    ADD COLUMN deleted_at SimpleAggregateFunction(any, Nullable(DateTime64(3)));

ALTER TABLE calls_merged_view MODIFY QUERY
    SELECT project_id,
        id,
        anySimpleState(wb_run_id) as wb_run_id,
        anySimpleState(wb_user_id) as wb_user_id,
        anySimpleState(trace_id) as trace_id,
        anySimpleState(parent_id) as parent_id,
        anySimpleState(op_name) as op_name,
        anySimpleState(started_at) as started_at,
        anySimpleState(attributes_dump) as attributes_dump,
        anySimpleState(inputs_dump) as inputs_dump,
        array_concat_aggSimpleState(input_refs) as input_refs,
        anySimpleState(ended_at) as ended_at,
        anySimpleState(output_dump) as output_dump,
        anySimpleState(summary_dump) as summary_dump,
        anySimpleState(exception) as exception,
        array_concat_aggSimpleState(output_refs) as output_refs,
        anySimpleState(deleted_at) as deleted_at
    FROM call_parts
    GROUP BY project_id,
        id;
