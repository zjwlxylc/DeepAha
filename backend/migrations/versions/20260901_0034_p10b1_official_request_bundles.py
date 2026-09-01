"""p10b1_official_request_bundles

Revision ID: 20260901_0034
Revises: 20260826_0033
Create Date: 2026-09-01 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0034"
down_revision: str | None = "20260826_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_bundles",
        sa.Column("request_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "source_bundles",
        sa.Column("request_payload_sha256", sa.String(length=64), nullable=True),
    )
    op.alter_column("source_bundles", "opportunity_id", nullable=True)
    op.create_check_constraint(
        op.f("ck_source_bundles_request_key_format"),
        "source_bundles",
        "request_key is null or request_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'",
    )
    op.create_check_constraint(
        op.f("ck_source_bundles_request_payload_sha256_format"),
        "source_bundles",
        "request_payload_sha256 is null or request_payload_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        op.f("ck_source_bundles_identity_binding"),
        "source_bundles",
        "(opportunity_id is not null and request_key is null and "
        "request_payload_sha256 is null) or "
        "(opportunity_id is null and request_key is not null and "
        "request_payload_sha256 is not null)",
    )
    op.create_index(
        "uq_source_bundles_request_key",
        "source_bundles",
        ["request_key"],
        unique=True,
        postgresql_where=sa.text("request_key is not null"),
    )
    _create_request_bundle_guard()

    op.drop_constraint(
        op.f("ck_source_bundle_revisions_positive_opportunity_version"),
        "source_bundle_revisions",
        type_="check",
    )
    op.alter_column("source_bundle_revisions", "opportunity_id", nullable=True)
    op.alter_column("source_bundle_revisions", "opportunity_version", nullable=True)
    op.create_check_constraint(
        op.f("ck_source_bundle_revisions_opportunity_binding"),
        "source_bundle_revisions",
        "(opportunity_id is null and opportunity_version is null) or "
        "(opportunity_id is not null and opportunity_version >= 1)",
    )
    op.create_foreign_key(
        "fk_source_bundle_revisions_bundle_only",
        "source_bundle_revisions",
        "source_bundles",
        ["source_bundle_id"],
        ["source_bundle_id"],
        ondelete="RESTRICT",
    )
    _create_revision_binding_guard()
    _replace_revision_null_comparisons(use_distinct=True)

    op.add_column(
        "source_bundle_members",
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "source_bundle_members",
        sa.Column("parse_attempt_id", sa.Uuid(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_source_bundle_members_evidence_parse_binding_pair"),
        "source_bundle_members",
        "(evidence_ref_id is null and parse_attempt_id is null) or "
        "(evidence_ref_id is not null and parse_attempt_id is not null)",
    )
    op.create_foreign_key(
        "fk_source_bundle_members_evidence_ref",
        "source_bundle_members",
        "evidence_refs",
        ["evidence_ref_id"],
        ["evidence_ref_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_source_bundle_members_parse_attempt",
        "source_bundle_members",
        "parse_attempts",
        ["parse_attempt_id"],
        ["parse_attempt_id"],
        ondelete="RESTRICT",
    )
    _replace_expected_member_hash(include_exact_evidence=True)
    _create_request_member_evidence_guard()
    _create_bound_evidence_immutability_guards()


def downgrade() -> None:
    connection = op.get_bind()
    has_request_history = connection.scalar(
        sa.text(
            "select exists (select 1 from source_bundles "
            "where request_key is not null or opportunity_id is null)"
        )
    )
    has_unbound_revision = connection.scalar(
        sa.text(
            "select exists (select 1 from source_bundle_revisions where opportunity_id is null)"
        )
    )
    has_exact_member_binding = connection.scalar(
        sa.text(
            "select exists (select 1 from source_bundle_members "
            "where evidence_ref_id is not null or parse_attempt_id is not null)"
        )
    )
    if has_request_history or has_unbound_revision or has_exact_member_binding:
        raise RuntimeError("cannot downgrade P10-B1 while request or exact-member history exists")

    op.execute("DROP TRIGGER p10b1_parse_attempt_immutability_guard ON parse_attempts")
    op.execute("DROP FUNCTION p10b1_guard_bound_parse_attempt()")
    op.execute("DROP TRIGGER p10b1_evidence_ref_immutability_guard ON evidence_refs")
    op.execute("DROP FUNCTION p10b1_guard_bound_evidence_ref()")
    op.execute("DROP TRIGGER p10b1_request_member_evidence_guard ON source_bundle_members")
    op.execute("DROP FUNCTION p10b1_guard_request_member_evidence()")
    _replace_expected_member_hash(include_exact_evidence=False)
    op.drop_constraint(
        "fk_source_bundle_members_parse_attempt",
        "source_bundle_members",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_source_bundle_members_evidence_ref",
        "source_bundle_members",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_source_bundle_members_evidence_parse_binding_pair"),
        "source_bundle_members",
        type_="check",
    )
    op.drop_column("source_bundle_members", "parse_attempt_id")
    op.drop_column("source_bundle_members", "evidence_ref_id")

    _replace_revision_null_comparisons(use_distinct=False)
    op.execute("DROP TRIGGER source_bundle_revisions_binding_guard ON source_bundle_revisions")
    op.execute("DROP FUNCTION p10b1_guard_bundle_revision_binding()")
    op.drop_constraint(
        "fk_source_bundle_revisions_bundle_only",
        "source_bundle_revisions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_source_bundle_revisions_opportunity_binding"),
        "source_bundle_revisions",
        type_="check",
    )
    op.alter_column("source_bundle_revisions", "opportunity_version", nullable=False)
    op.alter_column("source_bundle_revisions", "opportunity_id", nullable=False)
    op.create_check_constraint(
        op.f("ck_source_bundle_revisions_positive_opportunity_version"),
        "source_bundle_revisions",
        "opportunity_version >= 1",
    )

    op.execute("DROP TRIGGER source_bundles_request_identity_guard ON source_bundles")
    op.execute("DROP FUNCTION p10b1_guard_request_bundle_identity()")
    op.drop_index("uq_source_bundles_request_key", table_name="source_bundles")
    op.drop_constraint(
        op.f("ck_source_bundles_identity_binding"),
        "source_bundles",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_source_bundles_request_payload_sha256_format"),
        "source_bundles",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_source_bundles_request_key_format"),
        "source_bundles",
        type_="check",
    )
    op.alter_column("source_bundles", "opportunity_id", nullable=False)
    op.drop_column("source_bundles", "request_payload_sha256")
    op.drop_column("source_bundles", "request_key")


def _create_request_bundle_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p10b1_guard_request_bundle_identity()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.request_key IS NOT NULL AND TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'P10B1_REQUEST_BUNDLE_HISTORY_IMMUTABLE';
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.request_key IS NOT NULL AND (
                OLD.source_bundle_id IS DISTINCT FROM NEW.source_bundle_id
                OR OLD.opportunity_id IS DISTINCT FROM NEW.opportunity_id
                OR OLD.request_key IS DISTINCT FROM NEW.request_key
                OR OLD.request_payload_sha256 IS DISTINCT FROM NEW.request_payload_sha256
                OR OLD.created_at IS DISTINCT FROM NEW.created_at
            ) THEN
                RAISE EXCEPTION 'P10B1_REQUEST_BUNDLE_IDENTITY_IMMUTABLE';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER source_bundles_request_identity_guard BEFORE UPDATE OR DELETE ON "
        "source_bundles FOR EACH ROW EXECUTE FUNCTION p10b1_guard_request_bundle_identity()"
    )


def _create_revision_binding_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p10b1_guard_bundle_revision_binding()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM source_bundles AS bundle
                WHERE bundle.source_bundle_id = NEW.source_bundle_id
                  AND bundle.opportunity_id IS NOT DISTINCT FROM NEW.opportunity_id
            ) THEN
                RAISE EXCEPTION 'P10B1_BUNDLE_REVISION_BINDING_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER source_bundle_revisions_binding_guard BEFORE INSERT OR UPDATE OF "
        "source_bundle_id, opportunity_id ON source_bundle_revisions FOR EACH ROW "
        "EXECUTE FUNCTION p10b1_guard_bundle_revision_binding()"
    )


def _create_request_member_evidence_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p10b1_guard_request_member_evidence()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM source_bundle_revisions AS revision
                JOIN source_bundles AS bundle
                  ON bundle.source_bundle_id = revision.source_bundle_id
                WHERE revision.source_bundle_revision_id = NEW.source_bundle_revision_id
                  AND bundle.request_key IS NOT NULL
            ) THEN
                IF NEW.evidence_ref_id IS NULL OR NEW.parse_attempt_id IS NULL THEN
                    RAISE EXCEPTION 'P10B1_REQUEST_MEMBER_EXACT_EVIDENCE_REQUIRED';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM evidence_refs AS evidence
                    WHERE evidence.evidence_ref_id = NEW.evidence_ref_id
                      AND evidence.document_id = NEW.document_id
                      AND evidence.artifact_id = NEW.raw_artifact_id
                      AND evidence.locator_kind = 'full_document'
                      AND evidence.locator_value = '*'
                      AND evidence.locator_schema_version = '0.1.0'
                      AND evidence.quote_sha256 = NEW.raw_artifact_sha256
                ) THEN
                    RAISE EXCEPTION 'P10B1_REQUEST_MEMBER_EVIDENCE_MISMATCH';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM parse_attempts AS attempt
                    WHERE attempt.parse_attempt_id = NEW.parse_attempt_id
                      AND attempt.document_id = NEW.document_id
                      AND attempt.artifact_id = NEW.raw_artifact_id
                      AND attempt.document_parse_key = NEW.document_parse_key
                      AND attempt.parser_name = NEW.parser_name
                      AND attempt.parser_version = NEW.parser_version
                      AND attempt.parse_contract_version = NEW.parse_contract_version
                      AND attempt.outcome = 'SUCCEEDED'
                ) THEN
                    RAISE EXCEPTION 'P10B1_REQUEST_MEMBER_PARSE_MISMATCH';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p10b1_request_member_evidence_guard BEFORE INSERT OR UPDATE OF "
        "source_bundle_revision_id, evidence_ref_id, parse_attempt_id, document_id, "
        "raw_artifact_id, raw_artifact_sha256, document_parse_key, parser_name, "
        "parser_version, parse_contract_version ON source_bundle_members FOR EACH ROW "
        "EXECUTE FUNCTION p10b1_guard_request_member_evidence()"
    )


def _create_bound_evidence_immutability_guards() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p10b1_guard_bound_evidence_ref()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM source_bundle_members
                WHERE evidence_ref_id = OLD.evidence_ref_id
            ) THEN
                RAISE EXCEPTION 'P10B1_BOUND_EVIDENCE_REF_IMMUTABLE';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p10b1_evidence_ref_immutability_guard BEFORE UPDATE OR DELETE ON "
        "evidence_refs FOR EACH ROW EXECUTE FUNCTION p10b1_guard_bound_evidence_ref()"
    )
    op.execute(
        r"""
        CREATE FUNCTION p10b1_guard_bound_parse_attempt()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM source_bundle_members
                WHERE parse_attempt_id = OLD.parse_attempt_id
            ) THEN
                RAISE EXCEPTION 'P10B1_BOUND_PARSE_ATTEMPT_IMMUTABLE';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p10b1_parse_attempt_immutability_guard BEFORE UPDATE OR DELETE ON "
        "parse_attempts FOR EACH ROW EXECUTE FUNCTION p10b1_guard_bound_parse_attempt()"
    )


def _replace_expected_member_hash(*, include_exact_evidence: bool) -> None:
    exact_evidence = (
        " || CASE WHEN member.evidence_ref_id IS NULL THEN '{}'::jsonb ELSE "
        "jsonb_build_object('evidence_ref_id', member.evidence_ref_id::text, "
        "'parse_attempt_id', member.parse_attempt_id::text) END"
        if include_exact_evidence
        else ""
    )
    definition = r"""
        CREATE OR REPLACE FUNCTION p9b_expected_member_hash(member_id uuid)
        RETURNS text LANGUAGE sql STABLE STRICT AS $$
            SELECT p9b_hash_json(
                'member_provenance_hash',
                jsonb_build_object(
                    'source_bundle_member_id', member.source_bundle_member_id::text,
                    'source_bundle_revision_id', member.source_bundle_revision_id::text,
                    'source_id', member.source_id::text,
                    'endpoint_id', member.endpoint_id::text,
                    'capture_observation_id', member.capture_observation_id::text,
                    'acquisition_evaluation_id', member.acquisition_evaluation_id::text,
                    'acquisition_validation_status', member.acquisition_validation_status,
                    'acquisition_run_id', member.acquisition_run_id::text,
                    'recipe_id', member.recipe_id::text,
                    'recipe_version', member.recipe_version,
                    'policy_version', member.policy_version,
                    'fetch_strategy', member.fetch_strategy,
                    'fetcher_name', member.fetcher_name,
                    'fetcher_version', member.fetcher_version,
                    'validator_name', member.validator_name,
                    'validator_version', member.validator_version,
                    'raw_artifact_id', member.raw_artifact_id::text,
                    'raw_artifact_sha256', member.raw_artifact_sha256,
                    'raw_artifact_size', member.raw_artifact_size,
                    'storage_bucket', member.storage_bucket,
                    'object_key', member.object_key,
                    'document_id', member.document_id::text,
                    'document_parse_key', member.document_parse_key,
                    'parser_name', member.parser_name,
                    'parser_version', member.parser_version,
                    'parse_contract_version', member.parse_contract_version,
                    'member_role', member.member_role,
                    'relation_type', COALESCE(relation.relation_type, 'PRIMARY'),
                    'precedence', member.precedence,
                    'related_member_id', relation.target_member_id::text,
                    'effective_from', CASE WHEN member.effective_from IS NULL THEN NULL
                                           ELSE p9b_instant(member.effective_from) END,
                    'effective_to', CASE WHEN member.effective_to IS NULL THEN NULL
                                         ELSE p9b_instant(member.effective_to) END
                )
                __EXACT_EVIDENCE__
            )
            FROM source_bundle_members AS member
            LEFT JOIN LATERAL (
                SELECT edge.relation_type, edge.target_member_id
                FROM source_bundle_member_relations AS edge
                WHERE edge.source_bundle_revision_id = member.source_bundle_revision_id
                  AND edge.source_member_id = member.source_bundle_member_id
                ORDER BY edge.target_member_id, edge.relation_type
                LIMIT 1
            ) AS relation ON true
            WHERE member.source_bundle_member_id = member_id
        $$
    """.replace("__EXACT_EVIDENCE__", exact_evidence)
    op.execute(definition)


def _replace_revision_null_comparisons(*, use_distinct: bool) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        sa.text("select pg_get_functiondef(to_regprocedure(:signature))"),
        {"signature": "p9b_guard_bundle_revision_update()"},
    )
    if not isinstance(definition, str):
        raise RuntimeError("P9-B bundle revision guard is missing")
    replacements = (
        (
            "OLD.opportunity_id <> NEW.opportunity_id",
            "OLD.opportunity_id IS DISTINCT FROM NEW.opportunity_id",
        ),
        (
            "OLD.opportunity_version <> NEW.opportunity_version",
            "OLD.opportunity_version IS DISTINCT FROM NEW.opportunity_version",
        ),
    )
    for legacy, null_safe in replacements:
        current, replacement = (legacy, null_safe) if use_distinct else (null_safe, legacy)
        if replacement in definition:
            continue
        if current not in definition:
            raise RuntimeError("P9-B bundle revision guard shape is unsupported")
        definition = definition.replace(current, replacement)
    connection.exec_driver_sql(definition.replace("%", "%%"))
