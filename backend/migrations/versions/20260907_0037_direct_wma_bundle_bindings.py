"""Add explicit Direct WMA provenance and append-only entity associations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260907_0037"
down_revision = "20260907_0036"
branch_labels = None
depends_on = None

ACQUISITION = (
    "capture_observation_id",
    "acquisition_evaluation_id",
    "acquisition_validation_status",
    "acquisition_run_id",
    "recipe_id",
    "recipe_version",
    "fetch_strategy",
    "fetcher_name",
    "fetcher_version",
    "validator_name",
    "validator_version",
)
WMA = ("wma_task_id", "wma_material_id", "wma_delivery_hash", "wma_contract_hash")


def _member_hash(*, upgrade: bool) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text("select pg_get_functiondef('p9b_expected_member_hash(uuid)'::regprocedure)")
    )
    if not isinstance(definition, str):
        raise RuntimeError("P9B member hash function is missing")
    if upgrade:
        marker = "\n            )\n            FROM source_bundle_members"
        if marker not in definition or "DIRECT_WMA_START" in definition:
            raise RuntimeError("Unsupported P9B member hash definition")
        # Append to the existing JSON expression. Legacy payloads and their frozen
        # hashes remain byte-for-byte unchanged; no historical row is rewritten.
        suffix = """
                /* DIRECT_WMA_START */
                - CASE WHEN member.provenance_kind = 'DIRECT_WMA'
                  THEN ARRAY[__ACQUISITION__] ELSE ARRAY[]::text[] END
                || CASE WHEN member.provenance_kind = 'DIRECT_WMA' THEN jsonb_build_object(
                    'provenance_kind', 'DIRECT_WMA',
                    'provenance_version', 'direct-wma-member/1',
                    'url_provenance', 'AGENT_DECLARED',
                    'wma_task_id', member.wma_task_id::text,
                    'wma_material_id', member.wma_material_id,
                    'wma_delivery_hash', member.wma_delivery_hash,
                    'wma_contract_hash', member.wma_contract_hash
                ) ELSE '{}'::jsonb END
                /* DIRECT_WMA_END */""".replace(
            "__ACQUISITION__", ",".join(repr(column) for column in ACQUISITION)
        )
        # Parenthesize the old expression so subtraction also applies to the
        # optional EvidenceRef/ParseAttempt concatenation introduced in 0034.
        start = definition.index("jsonb_build_object(")
        end = definition.index(marker)
        definition = (
            definition[:start] + "(" + definition[start:end] + ")" + suffix + definition[end:]
        )
    else:
        start = definition.index("(jsonb_build_object(")
        suffix_start = definition.index("\n                /* DIRECT_WMA_START */")
        suffix_end = definition.index("/* DIRECT_WMA_END */") + len("/* DIRECT_WMA_END */")
        definition = (
            definition[:start] + definition[start + 1 : suffix_start - 1] + definition[suffix_end:]
        )
    connection.exec_driver_sql(definition.replace("%", "%%"))


def upgrade() -> None:
    op.add_column(
        "source_bundle_members",
        sa.Column("provenance_kind", sa.String(16), nullable=False, server_default="ACQUISITION"),
    )
    for column, kind in (
        ("wma_task_id", sa.Uuid()),
        ("wma_material_id", sa.String(256)),
        ("wma_delivery_hash", sa.String(64)),
        ("wma_contract_hash", sa.String(64)),
    ):
        op.add_column("source_bundle_members", sa.Column(column, kind, nullable=True))
    for column in ACQUISITION:
        op.alter_column("source_bundle_members", column, nullable=True)
    shape = (
        "(provenance_kind = 'ACQUISITION' and "
        + " and ".join(f"{column} is not null" for column in ACQUISITION)
        + " and "
        + " and ".join(f"{column} is null" for column in WMA)
        + ") or (provenance_kind = 'DIRECT_WMA' and "
        + " and ".join(f"{column} is null" for column in ACQUISITION)
        + " and "
        + " and ".join(f"{column} is not null" for column in WMA)
        + " and wma_delivery_hash ~ '^[0-9a-f]{64}$' and wma_contract_hash ~ '^[0-9a-f]{64}$'"
        + " and evidence_ref_id is not null and parse_attempt_id is not null)"
    )
    op.create_check_constraint("provenance_shape", "source_bundle_members", shape)
    op.create_foreign_key(
        "fk_source_bundle_members_wma_material",
        "source_bundle_members",
        "investigation_materials",
        ["wma_task_id", "wma_material_id"],
        ["task_id", "material_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_source_bundle_members_revision_document_role", "source_bundle_members", type_="unique"
    )
    op.create_index(
        "uq_source_bundle_members_revision_document_role",
        "source_bundle_members",
        ["source_bundle_revision_id", "document_id", "document_parse_key", "member_role"],
        unique=True,
        postgresql_where=sa.text("provenance_kind = 'ACQUISITION'"),
    )
    op.create_index(
        "uq_source_bundle_members_revision_wma_material",
        "source_bundle_members",
        ["source_bundle_revision_id", "wma_task_id", "wma_material_id"],
        unique=True,
        postgresql_where=sa.text("provenance_kind = 'DIRECT_WMA'"),
    )
    _member_hash(upgrade=True)
    _lineage_guards()
    op.create_table(
        "investigation_bindings",
        sa.Column("binding_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("investigation_tasks.task_id"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("delivery_hash", sa.String(64), nullable=False),
        sa.Column(
            "source_bundle_revision_id",
            sa.Uuid(),
            sa.ForeignKey("source_bundle_revisions.source_bundle_revision_id"),
            nullable=False,
        ),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
        ),
        sa.UniqueConstraint("task_id", "sequence", name="uq_investigation_bindings_sequence"),
        sa.UniqueConstraint(
            "task_id", "reviewer_id", "request_key_hash", name="uq_investigation_bindings_request"
        ),
        sa.CheckConstraint("uuid_extract_version(binding_id) = 7", name="binding_id_uuid7"),
        sa.CheckConstraint("sequence >= 1 and opportunity_version >= 1", name="positive_versions"),
        sa.CheckConstraint("jsonb_typeof(request) = 'object'", name="request_object"),
        sa.CheckConstraint(
            "delivery_hash ~ '^[0-9a-f]{64}$' and request_key_hash ~ '^[0-9a-f]{64}$' "
            "and request_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
    )
    _binding_guard()


def _lineage_guards() -> None:
    op.execute("""
    CREATE FUNCTION investigation_member_lineage_valid(member source_bundle_members)
    RETURNS boolean LANGUAGE sql STABLE STRICT AS $$
        SELECT EXISTS (
            SELECT 1 FROM investigation_tasks task
            JOIN investigation_materials material ON material.task_id = task.task_id
            JOIN parse_attempts attempt ON attempt.parse_attempt_id = member.parse_attempt_id
            JOIN evidence_refs evidence ON evidence.evidence_ref_id = member.evidence_ref_id
            WHERE task.task_id = member.wma_task_id AND material.material_id =
            member.wma_material_id
              AND task.status = 'APPROVED' AND task.runtime_id IS NOT NULL AND
              task.remote_session_id IS NOT NULL
              AND task.delivery_hash = member.wma_delivery_hash AND task.contract_hash =
              member.wma_contract_hash
              AND task.source_id = member.source_id AND task.endpoint_id = member.endpoint_id
              AND task.source_snapshot->>'policy_version' = member.policy_version
              AND material.raw_artifact_id = member.raw_artifact_id
              AND material.metadata_snapshot->>'sha256' = member.raw_artifact_sha256
              AND EXISTS (
                  SELECT 1 FROM jsonb_array_elements(task.delivery->'evidence'->'artifacts') item
                  WHERE item->>'artifact_id' = member.wma_material_id
                    AND lower(item->>'sha256') = member.raw_artifact_sha256
                    AND item->>'source_url' = material.metadata_snapshot->>'url'
              )
              AND attempt.outcome = 'SUCCEEDED' AND attempt.document_id = member.document_id
              AND attempt.artifact_id = member.raw_artifact_id
              AND attempt.document_parse_key = member.document_parse_key
              AND attempt.parser_name = member.parser_name AND attempt.parser_version =
              member.parser_version
              AND attempt.parse_contract_version = member.parse_contract_version
              AND evidence.document_id = member.document_id AND evidence.artifact_id =
              member.raw_artifact_id
              AND evidence.locator_kind = 'full_document' AND evidence.locator_value = '*'
              AND evidence.locator_schema_version = '0.1.0' AND evidence.quote_sha256 =
              member.raw_artifact_sha256
        )
    $$;
    CREATE FUNCTION investigation_guard_wma_member() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.provenance_kind = 'DIRECT_WMA' AND NOT investigation_member_lineage_valid(NEW) THEN
            RAISE EXCEPTION 'WMA_MEMBER_LINEAGE_MISMATCH';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_wma_member_guard BEFORE INSERT ON source_bundle_members
    FOR EACH ROW EXECUTE FUNCTION investigation_guard_wma_member();
    CREATE FUNCTION investigation_guard_wma_freeze() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.status = 'FROZEN' AND EXISTS (
            SELECT 1 FROM source_bundle_members member
            WHERE member.source_bundle_revision_id = NEW.source_bundle_revision_id
              AND member.provenance_kind = 'DIRECT_WMA' AND NOT
              investigation_member_lineage_valid(member)
        ) THEN RAISE EXCEPTION 'WMA_MEMBER_FREEZE_LINEAGE_MISMATCH'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_wma_freeze_guard BEFORE UPDATE ON source_bundle_revisions
    FOR EACH ROW EXECUTE FUNCTION investigation_guard_wma_freeze();
    CREATE FUNCTION investigation_guard_material_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE task investigation_tasks;
    BEGIN
        SELECT * INTO task FROM investigation_tasks WHERE task_id = NEW.task_id FOR UPDATE;
        IF task.status IS DISTINCT FROM 'COLLECTING' OR task.delivery_hash IS NOT NULL THEN
            RAISE EXCEPTION 'INVESTIGATION_MATERIAL_SET_FROZEN';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_material_insert_guard BEFORE INSERT ON investigation_materials
    FOR EACH ROW EXECUTE FUNCTION investigation_guard_material_insert();
    """)


def _binding_guard() -> None:
    op.execute("""
    CREATE FUNCTION investigation_guard_binding() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE task investigation_tasks; previous investigation_bindings; position jsonb;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'INVESTIGATION_BINDING_IMMUTABLE'; END IF;
        SELECT * INTO task FROM investigation_tasks WHERE task_id = NEW.task_id FOR UPDATE;
        SELECT * INTO previous FROM investigation_bindings WHERE task_id = NEW.task_id ORDER BY
        sequence DESC LIMIT 1;
        IF task.status IS DISTINCT FROM 'APPROVED' OR task.delivery_hash IS DISTINCT FROM
        NEW.delivery_hash
           OR NEW.sequence <> COALESCE(previous.sequence, 0) + 1
           OR (NEW.request->>'previous_binding_id') IS DISTINCT FROM previous.binding_id::text
           OR NEW.request->>'delivery_hash' IS DISTINCT FROM NEW.delivery_hash
           OR NEW.request->>'opportunity_id' IS DISTINCT FROM NEW.opportunity_id::text
           OR (NEW.request->>'opportunity_version')::integer IS DISTINCT FROM
           NEW.opportunity_version
           OR length(btrim(COALESCE(NEW.request->>'reason', ''))) NOT BETWEEN 1 AND 2000
           OR NEW.request_hash <> encode(sha256(convert_to(p9b_canonical_json(NEW.request),
           'UTF8')), 'hex')
           OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id = NEW.reviewer_id
               AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
               AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
           OR NOT EXISTS (SELECT 1 FROM opportunities WHERE opportunity_id = NEW.opportunity_id
               AND current_version = NEW.opportunity_version)
           OR NOT EXISTS (SELECT 1 FROM source_bundle_revisions WHERE source_bundle_revision_id =
           NEW.source_bundle_revision_id
               AND status = 'FROZEN' AND opportunity_id = NEW.opportunity_id AND
               opportunity_version = NEW.opportunity_version)
           OR EXISTS (SELECT 1 FROM source_bundle_members WHERE source_bundle_revision_id =
           NEW.source_bundle_revision_id
               AND (provenance_kind <> 'DIRECT_WMA' OR wma_task_id IS DISTINCT FROM NEW.task_id
                    OR wma_delivery_hash IS DISTINCT FROM NEW.delivery_hash))
           OR (SELECT count(*) FROM source_bundle_members WHERE source_bundle_revision_id =
           NEW.source_bundle_revision_id)
              <> (SELECT count(*) FROM investigation_materials WHERE task_id = NEW.task_id)
           OR (task.delivery->>'material_count')::integer IS DISTINCT FROM
              (SELECT count(*) FROM investigation_materials WHERE task_id = NEW.task_id)
           OR (SELECT count(DISTINCT wma_material_id) FROM source_bundle_members
               WHERE source_bundle_revision_id = NEW.source_bundle_revision_id)
              <> (SELECT count(*) FROM investigation_materials WHERE task_id = NEW.task_id)
        THEN RAISE EXCEPTION 'INVESTIGATION_BINDING_MISMATCH'; END IF;
        IF jsonb_typeof(NEW.request->'positions') IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'INVESTIGATION_POSITION_BINDING_MISMATCH';
        END IF;
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.request->'positions') item GROUP BY
        item->>'entity_id' HAVING count(*) > 1)
           OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.request->'positions') item GROUP BY
           item->>'opportunity_unit_id' HAVING count(*) > 1)
        THEN RAISE EXCEPTION 'INVESTIGATION_POSITION_BINDING_DUPLICATE'; END IF;
        FOR position IN SELECT * FROM jsonb_array_elements(NEW.request->'positions') LOOP
            IF NOT EXISTS (SELECT 1 FROM
            jsonb_array_elements(task.delivery->'evidence'->'entities') entity
                WHERE entity->>'id' = position->>'entity_id' AND entity->>'kind' = 'position')
               OR NOT EXISTS (SELECT 1 FROM opportunity_unit_versions version JOIN
               opportunity_units unit
                    ON unit.opportunity_unit_id = version.opportunity_unit_id
                WHERE version.opportunity_unit_version_id::text =
                position->>'opportunity_unit_version_id'
                  AND version.opportunity_unit_id::text = position->>'opportunity_unit_id'
                  AND version.opportunity_id = NEW.opportunity_id AND version.opportunity_version
                  = NEW.opportunity_version
                  AND version.status = 'ACTIVE' AND unit.lifecycle_status = 'ACTIVE' AND
                  unit.unit_kind = 'POSITION'
                  AND unit.current_version_id = version.opportunity_unit_version_id)
            THEN RAISE EXCEPTION 'INVESTIGATION_POSITION_BINDING_MISMATCH'; END IF;
        END LOOP;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_binding_guard BEFORE INSERT OR UPDATE OR DELETE ON
    investigation_bindings
    FOR EACH ROW EXECUTE FUNCTION investigation_guard_binding();
    """)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "select exists(select 1 from source_bundle_members "
            "where provenance_kind = 'DIRECT_WMA') "
            "or exists(select 1 from investigation_bindings)"
        )
    ):
        raise RuntimeError("Cannot remove WMA provenance or entity association history")
    op.drop_table("investigation_bindings")
    op.execute("DROP TRIGGER investigation_material_insert_guard ON investigation_materials")
    op.execute("DROP FUNCTION investigation_guard_material_insert()")
    op.execute("DROP FUNCTION investigation_guard_binding()")
    op.execute("DROP TRIGGER investigation_wma_freeze_guard ON source_bundle_revisions")
    op.execute("DROP FUNCTION investigation_guard_wma_freeze()")
    op.execute("DROP TRIGGER investigation_wma_member_guard ON source_bundle_members")
    op.execute("DROP FUNCTION investigation_guard_wma_member()")
    op.execute("DROP FUNCTION investigation_member_lineage_valid(source_bundle_members)")
    _member_hash(upgrade=False)
    op.drop_index(
        "uq_source_bundle_members_revision_wma_material", table_name="source_bundle_members"
    )
    op.drop_index(
        "uq_source_bundle_members_revision_document_role", table_name="source_bundle_members"
    )
    op.create_unique_constraint(
        "uq_source_bundle_members_revision_document_role",
        "source_bundle_members",
        ["source_bundle_revision_id", "document_id", "document_parse_key", "member_role"],
    )
    op.drop_constraint(
        "fk_source_bundle_members_wma_material", "source_bundle_members", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("ck_source_bundle_members_provenance_shape"), "source_bundle_members", type_="check"
    )
    for column in ACQUISITION:
        op.alter_column("source_bundle_members", column, nullable=False)
    for column in (*WMA, "provenance_kind"):
        op.drop_column("source_bundle_members", column)
