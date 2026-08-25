"""p9b_replacement_provenance_identity_integrity

Revision ID: 20260825_0023
Revises: 20260824_0014
Create Date: 2026-08-24 23:00:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0023"
down_revision: str | None = "20260824_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    _create_hash_proof_functions()
    _serialize_member_graph_mutations()
    _assert_existing_frozen_provenance()
    _replace_bundle_freeze_guard()
    _repair_unit_current_binding()
    _repair_alias_lifecycle()


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "select exists(select 1 from source_bundle_revisions limit 1) "
            "or exists(select 1 from opportunity_units limit 1)"
        )
    ).scalar_one():
        raise RuntimeError("cannot downgrade P9-B provenance/identity repairs with history")

    op.execute("DROP TRIGGER opportunity_units_current_version_guard ON opportunity_units")
    op.execute("DROP FUNCTION p9b_guard_unit_current_version()")
    op.drop_constraint(
        "fk_opportunity_units_current_version", "opportunity_units", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_opportunity_units_current_version",
        "opportunity_units",
        "opportunity_unit_versions",
        ["opportunity_unit_id", "current_version_id"],
        ["opportunity_unit_id", "opportunity_unit_version_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
    )

    op.drop_index("uq_opportunity_unit_aliases_current", table_name="opportunity_unit_aliases")
    op.execute("DROP TRIGGER opportunity_unit_aliases_reject_mutation ON opportunity_unit_aliases")
    op.execute("DROP FUNCTION p9b_guard_alias_lifecycle()")
    op.execute(
        "DROP TRIGGER opportunity_unit_current_alias_exactly_one ON opportunity_unit_aliases"
    )
    op.execute("DROP TRIGGER opportunity_units_current_alias_exactly_one ON opportunity_units")
    op.execute("DROP FUNCTION p9b_require_exact_current_alias()")
    op.execute(
        "CREATE TRIGGER opportunity_unit_aliases_reject_mutation BEFORE UPDATE OR DELETE "
        "ON opportunity_unit_aliases FOR EACH ROW EXECUTE FUNCTION "
        "p9b_reject_immutable_mutation()"
    )

    _restore_legacy_bundle_guard()
    _restore_legacy_member_graph_guard()
    op.execute("DROP FUNCTION p9b_expected_bundle_hash(uuid)")
    op.execute("DROP FUNCTION p9b_expected_member_hash(uuid)")
    op.execute("DROP FUNCTION p9b_hash_json(text, jsonb)")
    op.execute("DROP FUNCTION p9b_canonical_json(jsonb)")
    op.execute("DROP FUNCTION p9b_instant(timestamptz)")


def _create_hash_proof_functions() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_instant(value timestamptz)
        RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT to_char(value AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') ||
                   CASE WHEN to_char(value AT TIME ZONE 'UTC', 'US') = '000000'
                        THEN ''
                        ELSE '.' || rtrim(to_char(value AT TIME ZONE 'UTC', 'US'), '0')
                   END || 'Z'
        $$
        """
    )


def _assert_existing_frozen_provenance() -> None:
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM source_bundle_revisions AS revision
                WHERE revision.status IN ('FROZEN', 'INVALIDATED')
                  AND NOT EXISTS (
                      SELECT 1 FROM source_bundle_members AS member
                      WHERE member.source_bundle_revision_id = revision.source_bundle_revision_id
                  )
            ) THEN
                RAISE EXCEPTION 'P9B_EXISTING_FROZEN_PROVENANCE_INVALID: empty revision';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM source_bundle_revisions AS revision
                JOIN source_bundle_member_relations AS relation
                  ON relation.source_bundle_revision_id = revision.source_bundle_revision_id
                WHERE revision.status IN ('FROZEN', 'INVALIDATED')
                GROUP BY revision.source_bundle_revision_id, relation.source_member_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'P9B_EXISTING_FROZEN_PROVENANCE_INVALID: relation multiplicity';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM source_bundle_revisions AS revision
                JOIN source_bundle_members AS member
                  ON member.source_bundle_revision_id = revision.source_bundle_revision_id
                JOIN acquisition_runs AS run
                  ON run.acquisition_run_id = member.acquisition_run_id
                WHERE revision.status IN ('FROZEN', 'INVALIDATED')
                  AND (
                      member.acquisition_validation_status <> 'VALID'
                      OR NOT EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements(run.strategy_attempts) AS attempt
                          WHERE attempt->>'capture_observation_id' =
                                member.capture_observation_id::text
                            AND attempt->>'acquisition_evaluation_id' =
                                member.acquisition_evaluation_id::text
                            AND attempt->>'raw_artifact_id' = member.raw_artifact_id::text
                      )
                      OR member.member_provenance_hash IS DISTINCT FROM
                         p9b_expected_member_hash(member.source_bundle_member_id)
                  )
            ) THEN
                RAISE EXCEPTION 'P9B_EXISTING_FROZEN_PROVENANCE_INVALID: member proof';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM source_bundle_revisions AS revision
                WHERE revision.status IN ('FROZEN', 'INVALIDATED')
                  AND revision.canonical_bundle_hash IS DISTINCT FROM
                      p9b_expected_bundle_hash(revision.source_bundle_revision_id)
            ) THEN
                RAISE EXCEPTION 'P9B_EXISTING_FROZEN_PROVENANCE_INVALID: bundle proof';
            END IF;
        END;
        $$
        """
    )


def _serialize_member_graph_mutations() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION p9b_require_draft_bundle_revision()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            revision_status text;
        BEGIN
            SELECT status INTO revision_status
            FROM source_bundle_revisions
            WHERE source_bundle_revision_id = NEW.source_bundle_revision_id
            FOR UPDATE;
            IF revision_status IS DISTINCT FROM 'DRAFT' THEN
                RAISE EXCEPTION 'SourceBundle member graph can only be added to a DRAFT revision';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_canonical_json(value jsonb)
        RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT CASE jsonb_typeof(value)
                WHEN 'object' THEN COALESCE(
                    (SELECT '{' || string_agg(
                        to_jsonb(item.key)::text || ':' || p9b_canonical_json(item.value),
                        ',' ORDER BY item.key
                    ) || '}' FROM jsonb_each(value) AS item),
                    '{}'
                )
                WHEN 'array' THEN COALESCE(
                    (SELECT '[' || string_agg(
                        p9b_canonical_json(item.value), ',' ORDER BY item.ordinality
                    ) || ']' FROM jsonb_array_elements(value)
                        WITH ORDINALITY AS item(value, ordinality)),
                    '[]'
                )
                ELSE value::text
            END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_hash_json(domain_name text, payload jsonb)
        RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT encode(
                digest(
                    convert_to(
                        'deepaha' || ':' || 'p9b' || ':' || domain_name ||
                        ':' || 'p9b-canonical-json-sha256-v1',
                        'UTF8'
                    ) || decode('00', 'hex') ||
                    convert_to(p9b_canonical_json(payload), 'UTF8'),
                    'sha256'
                ),
                'hex'
            )
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_expected_member_hash(member_id uuid)
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
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_expected_bundle_hash(revision_id uuid)
        RETURNS text LANGUAGE sql STABLE STRICT AS $$
            SELECT p9b_hash_json(
                'canonical_bundle_hash',
                jsonb_build_object(
                    'source_bundle_id', revision.source_bundle_id::text,
                    'source_bundle_revision_id', revision.source_bundle_revision_id::text,
                    'opportunity_id', revision.opportunity_id::text,
                    'opportunity_version', revision.opportunity_version,
                    'revision_number', revision.revision_number,
                    'effective_as_of', p9b_instant(revision.effective_as_of),
                    'relation_graph_version', revision.relation_graph_version,
                    'precedence_graph_version', revision.precedence_graph_version,
                    'member_provenance_hashes', COALESCE(
                        (SELECT jsonb_agg(member.member_provenance_hash
                                          ORDER BY member.source_bundle_member_id)
                         FROM source_bundle_members AS member
                         WHERE member.source_bundle_revision_id = revision.source_bundle_revision_id),
                        '[]'::jsonb
                    ),
                    'relations', COALESCE(
                        (SELECT jsonb_agg(
                            jsonb_build_object(
                                'source_member_id', edge.source_member_id::text,
                                'target_member_id', edge.target_member_id::text,
                                'relation_type', edge.relation_type
                            ) ORDER BY edge.source_member_id, edge.target_member_id,
                                       edge.relation_type
                         )
                         FROM source_bundle_member_relations AS edge
                         WHERE edge.source_bundle_revision_id = revision.source_bundle_revision_id),
                        '[]'::jsonb
                    )
                )
            )
            FROM source_bundle_revisions AS revision
            WHERE revision.source_bundle_revision_id = revision_id
        $$
        """
    )


def _replace_bundle_freeze_guard() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION p9b_guard_bundle_revision_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            member_count integer;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'SourceBundleRevision history cannot be deleted';
            END IF;
            IF OLD.source_bundle_revision_id <> NEW.source_bundle_revision_id
               OR OLD.source_bundle_id <> NEW.source_bundle_id
               OR OLD.opportunity_id <> NEW.opportunity_id
               OR OLD.opportunity_version <> NEW.opportunity_version
               OR OLD.revision_number <> NEW.revision_number
               OR (
                    OLD.canonical_bundle_hash <> NEW.canonical_bundle_hash
                    AND NOT (OLD.status = 'DRAFT' AND NEW.status = 'FROZEN')
               )
               OR OLD.relation_graph_version <> NEW.relation_graph_version
               OR OLD.precedence_graph_version <> NEW.precedence_graph_version
               OR OLD.effective_as_of <> NEW.effective_as_of
               OR OLD.created_at <> NEW.created_at
               OR NOT (
                    (OLD.status = 'DRAFT' AND NEW.status = 'FROZEN' AND NEW.frozen_at IS NOT NULL)
                    OR (OLD.status = 'FROZEN' AND NEW.status = 'INVALIDATED'
                        AND NEW.frozen_at = OLD.frozen_at)
               )
            THEN
                RAISE EXCEPTION 'SourceBundleRevision immutable fields or transition rejected';
            END IF;

            IF OLD.status = 'DRAFT' AND NEW.status = 'FROZEN' THEN
                SELECT count(*) INTO member_count
                FROM source_bundle_members
                WHERE source_bundle_revision_id = NEW.source_bundle_revision_id;
                IF member_count = 0 THEN
                    RAISE EXCEPTION 'P9B_BUNDLE_FREEZE_PROOF_MISMATCH: empty revision';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM source_bundle_member_relations
                    WHERE source_bundle_revision_id = NEW.source_bundle_revision_id
                    GROUP BY source_member_id HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION 'P9B_BUNDLE_FREEZE_PROOF_MISMATCH: relation multiplicity';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM source_bundle_members AS member
                    JOIN acquisition_runs AS run
                      ON run.acquisition_run_id = member.acquisition_run_id
                    WHERE member.source_bundle_revision_id = NEW.source_bundle_revision_id
                      AND (
                          member.acquisition_validation_status <> 'VALID'
                          OR NOT EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements(run.strategy_attempts) AS attempt
                          WHERE attempt->>'capture_observation_id' = member.capture_observation_id::text
                            AND attempt->>'acquisition_evaluation_id' = member.acquisition_evaluation_id::text
                            AND attempt->>'raw_artifact_id' = member.raw_artifact_id::text
                          )
                      )
                ) THEN
                    RAISE EXCEPTION 'P9B_BUNDLE_FREEZE_PROOF_MISMATCH: acquisition lineage';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM source_bundle_members AS member
                    WHERE member.source_bundle_revision_id = NEW.source_bundle_revision_id
                      AND member.member_provenance_hash <>
                          p9b_expected_member_hash(member.source_bundle_member_id)
                ) THEN
                    RAISE EXCEPTION 'P9B_BUNDLE_FREEZE_PROOF_MISMATCH: member hash';
                END IF;
                IF NEW.canonical_bundle_hash <>
                   p9b_expected_bundle_hash(NEW.source_bundle_revision_id) THEN
                    RAISE EXCEPTION 'P9B_BUNDLE_FREEZE_PROOF_MISMATCH: bundle hash';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )


def _repair_unit_current_binding() -> None:
    op.drop_constraint(
        "fk_opportunity_units_current_version", "opportunity_units", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_opportunity_units_current_version",
        "opportunity_units",
        "opportunity_unit_versions",
        [
            "opportunity_unit_id",
            "current_version_id",
            "opportunity_id",
            "opportunity_version",
        ],
        [
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "opportunity_id",
            "opportunity_version",
        ],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_unit_current_version()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.current_version_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM opportunity_unit_versions AS version
                WHERE version.opportunity_unit_id = NEW.opportunity_unit_id
                  AND version.opportunity_unit_version_id = NEW.current_version_id
                  AND version.opportunity_id = NEW.opportunity_id
                  AND version.opportunity_version = NEW.opportunity_version
            ) THEN
                RAISE EXCEPTION 'P9B_UNIT_CURRENT_VERSION_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER opportunity_units_current_version_guard BEFORE INSERT OR UPDATE "
        "ON opportunity_units FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_unit_current_version()"
    )


def _repair_alias_lifecycle() -> None:
    op.execute("DROP TRIGGER opportunity_unit_aliases_reject_mutation ON opportunity_unit_aliases")
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_alias_lifecycle()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT EXISTS (
                    SELECT 1
                    FROM opportunity_units AS unit
                    JOIN source_bundle_revisions AS revision
                      ON revision.source_bundle_revision_id = NEW.source_bundle_revision_id
                     AND revision.opportunity_id = unit.opportunity_id
                    JOIN evidence_refs AS evidence
                      ON evidence.evidence_ref_id = NEW.evidence_ref_id
                    JOIN source_bundle_members AS member
                      ON member.source_bundle_revision_id = revision.source_bundle_revision_id
                     AND member.document_id = evidence.document_id
                    WHERE unit.opportunity_unit_id = NEW.opportunity_unit_id
                      AND unit.opportunity_id = NEW.opportunity_id
                      AND revision.status = 'FROZEN'
                ) THEN
                    RAISE EXCEPTION 'P9B_UNIT_ALIAS_EVIDENCE_MISMATCH';
                END IF;
                IF NEW.alias_kind = 'CURRENT' AND NOT EXISTS (
                    SELECT 1 FROM opportunity_units AS unit
                    WHERE unit.opportunity_unit_id = NEW.opportunity_unit_id
                      AND unit.opportunity_id = NEW.opportunity_id
                      AND unit.lifecycle_status = 'ACTIVE'
                      AND unit.current_unit_key = NEW.display_alias_key
                      AND unit.normalized_current_unit_key = NEW.normalized_alias_key
                      AND NEW.valid_to IS NULL
                ) THEN
                    RAISE EXCEPTION 'P9B_UNIT_CURRENT_ALIAS_MISMATCH';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'P9-B alias history cannot be deleted';
            END IF;
            IF OLD.alias_kind = 'CURRENT'
               AND OLD.valid_to IS NULL
               AND NEW.alias_kind = 'HISTORICAL'
               AND NEW.valid_to > OLD.valid_from
               AND OLD.alias_id = NEW.alias_id
               AND OLD.opportunity_id = NEW.opportunity_id
               AND OLD.opportunity_unit_id = NEW.opportunity_unit_id
               AND OLD.normalized_alias_key = NEW.normalized_alias_key
               AND OLD.display_alias_key = NEW.display_alias_key
               AND OLD.valid_from = NEW.valid_from
               AND OLD.evidence_ref_id = NEW.evidence_ref_id
               AND OLD.source_bundle_revision_id = NEW.source_bundle_revision_id
               AND OLD.created_at = NEW.created_at
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'P9-B alias history mutation rejected';
        END;
        $$
        """
    )
    op.execute(
        r"""
        INSERT INTO opportunity_unit_aliases (
            alias_id, opportunity_id, opportunity_unit_id,
            normalized_alias_key, display_alias_key, alias_kind,
            valid_from, valid_to, evidence_ref_id,
            source_bundle_revision_id, created_at
        )
        SELECT uuidv7(), unit.opportunity_id, unit.opportunity_unit_id,
               unit.normalized_current_unit_key, unit.current_unit_key, 'CURRENT',
               version.effective_from, NULL, evidence.evidence_ref_id,
               version.source_bundle_revision_id, version.effective_from
        FROM opportunity_units AS unit
        JOIN opportunity_unit_versions AS version
          ON version.opportunity_unit_version_id = unit.current_version_id
         AND version.opportunity_unit_id = unit.opportunity_unit_id
        JOIN LATERAL (
            SELECT evidence_ref.evidence_ref_id
            FROM source_bundle_members AS member
            JOIN evidence_refs AS evidence_ref
              ON evidence_ref.document_id = member.document_id
            WHERE member.source_bundle_revision_id = version.source_bundle_revision_id
            ORDER BY evidence_ref.evidence_ref_id
            LIMIT 1
        ) AS evidence ON true
        WHERE unit.lifecycle_status = 'ACTIVE'
          AND NOT EXISTS (
              SELECT 1 FROM opportunity_unit_aliases AS alias
              WHERE alias.opportunity_unit_id = unit.opportunity_unit_id
                AND alias.alias_kind = 'CURRENT'
                AND alias.valid_to IS NULL
          )
        """
    )
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM opportunity_units AS unit
                LEFT JOIN opportunity_unit_aliases AS alias
                  ON alias.opportunity_unit_id = unit.opportunity_unit_id
                 AND alias.alias_kind = 'CURRENT'
                 AND alias.valid_to IS NULL
                WHERE unit.lifecycle_status = 'ACTIVE'
                GROUP BY unit.opportunity_unit_id, unit.opportunity_id,
                         unit.normalized_current_unit_key, unit.current_unit_key
                HAVING count(alias.alias_id) <> 1
                    OR bool_or(alias.opportunity_id IS DISTINCT FROM unit.opportunity_id)
                    OR bool_or(alias.normalized_alias_key IS DISTINCT FROM
                               unit.normalized_current_unit_key)
                    OR bool_or(alias.display_alias_key IS DISTINCT FROM unit.current_unit_key)
            ) THEN
                RAISE EXCEPTION 'P9B_ACTIVE_UNIT_CURRENT_ALIAS_BACKFILL_INCOMPLETE';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER opportunity_unit_aliases_reject_mutation BEFORE INSERT OR UPDATE OR DELETE "
        "ON opportunity_unit_aliases FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_alias_lifecycle()"
    )
    op.create_index(
        "uq_opportunity_unit_aliases_current",
        "opportunity_unit_aliases",
        ["opportunity_unit_id"],
        unique=True,
        postgresql_where=sa.text("alias_kind = 'CURRENT' and valid_to is null"),
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_require_exact_current_alias()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            affected_unit_id uuid;
            unit_row opportunity_units%ROWTYPE;
            matching_count integer;
            current_count integer;
        BEGIN
            affected_unit_id := CASE WHEN TG_OP = 'DELETE'
                                     THEN OLD.opportunity_unit_id
                                     ELSE NEW.opportunity_unit_id END;
            SELECT * INTO unit_row FROM opportunity_units
            WHERE opportunity_unit_id = affected_unit_id;
            IF NOT FOUND THEN
                RETURN NULL;
            END IF;
            SELECT count(*), count(*) FILTER (
                WHERE alias.opportunity_id = unit_row.opportunity_id
                  AND alias.normalized_alias_key = unit_row.normalized_current_unit_key
                  AND alias.display_alias_key = unit_row.current_unit_key
            )
            INTO current_count, matching_count
            FROM opportunity_unit_aliases AS alias
            WHERE alias.opportunity_unit_id = affected_unit_id
              AND alias.alias_kind = 'CURRENT'
              AND alias.valid_to IS NULL;
            IF unit_row.lifecycle_status = 'ACTIVE' AND
               (current_count <> 1 OR matching_count <> 1) THEN
                RAISE EXCEPTION 'P9B_ACTIVE_UNIT_CURRENT_ALIAS_MISMATCH';
            END IF;
            IF unit_row.lifecycle_status <> 'ACTIVE' AND current_count <> 0 THEN
                RAISE EXCEPTION 'P9B_RETIRED_UNIT_CURRENT_ALIAS_MISMATCH';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER opportunity_unit_current_alias_exactly_one "
        "AFTER INSERT OR UPDATE OR DELETE ON opportunity_unit_aliases "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
        "p9b_require_exact_current_alias()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER opportunity_units_current_alias_exactly_one "
        "AFTER INSERT OR UPDATE ON opportunity_units DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION p9b_require_exact_current_alias()"
    )


def _restore_legacy_bundle_guard() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION p9b_guard_bundle_revision_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'SourceBundleRevision history cannot be deleted';
            END IF;
            IF OLD.source_bundle_revision_id <> NEW.source_bundle_revision_id
               OR OLD.source_bundle_id <> NEW.source_bundle_id
               OR OLD.opportunity_id <> NEW.opportunity_id
               OR OLD.opportunity_version <> NEW.opportunity_version
               OR OLD.revision_number <> NEW.revision_number
               OR (
                    OLD.canonical_bundle_hash <> NEW.canonical_bundle_hash
                    AND NOT (OLD.status = 'DRAFT' AND NEW.status = 'FROZEN')
               )
               OR OLD.relation_graph_version <> NEW.relation_graph_version
               OR OLD.precedence_graph_version <> NEW.precedence_graph_version
               OR OLD.effective_as_of <> NEW.effective_as_of
               OR OLD.created_at <> NEW.created_at
               OR NOT (
                    (OLD.status = 'DRAFT' AND NEW.status = 'FROZEN' AND NEW.frozen_at IS NOT NULL)
                    OR (OLD.status = 'FROZEN' AND NEW.status = 'INVALIDATED'
                        AND NEW.frozen_at = OLD.frozen_at)
               )
            THEN
                RAISE EXCEPTION 'SourceBundleRevision immutable fields or transition rejected';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )


def _restore_legacy_member_graph_guard() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION p9b_require_draft_bundle_revision()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM source_bundle_revisions
                WHERE source_bundle_revision_id = NEW.source_bundle_revision_id
                  AND status = 'DRAFT'
            ) THEN
                RAISE EXCEPTION 'SourceBundle member graph can only be added to a DRAFT revision';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
