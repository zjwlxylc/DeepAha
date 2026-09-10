"""Append-only complete group source associations with real identity ownership."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260910_0046"
down_revision = "20260910_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_group_bindings",
        sa.Column("group_binding_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("investigation_tasks.task_id"), nullable=False
        ),
        sa.Column(
            "binding_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_bindings.binding_id"),
            nullable=False,
        ),
        sa.Column("source_entity_id", sa.String(256), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "unit_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity_units.opportunity_unit_id"),
            nullable=False,
        ),
        sa.Column(
            "unit_version_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity_unit_versions.opportunity_unit_version_id"),
            nullable=False,
        ),
        sa.Column("source", JSONB(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "task_id", "source_entity_id", "sequence", name="uq_investigation_group_sequence"
        ),
        sa.UniqueConstraint(
            "binding_id", "source_entity_id", name="uq_investigation_group_binding_entity"
        ),
        sa.CheckConstraint("uuid_extract_version(group_binding_id) = 7", name="id_uuid7"),
        sa.CheckConstraint("sequence >= 1", name="positive_sequence"),
        sa.CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        sa.CheckConstraint("jsonb_typeof(source) = 'object'", name="source_object"),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_group_binding() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE t investigation_tasks; b investigation_bindings; bundle source_bundle_revisions;
        u opportunity_units; v opportunity_unit_versions; prior investigation_group_bindings;
        raw_group jsonb; raw_entity jsonb; members jsonb; expected jsonb; group_key text;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'GROUP_SOURCE_IMMUTABLE'; END IF;
        SELECT * INTO STRICT t FROM investigation_tasks WHERE task_id=NEW.task_id FOR UPDATE;
        SELECT * INTO STRICT b FROM investigation_bindings WHERE binding_id=NEW.binding_id;
        SELECT * INTO STRICT bundle FROM source_bundle_revisions
            WHERE source_bundle_revision_id=b.source_bundle_revision_id;
        SELECT * INTO STRICT u FROM opportunity_units
            WHERE opportunity_unit_id=NEW.unit_id FOR UPDATE;
        SELECT * INTO STRICT v FROM opportunity_unit_versions
            WHERE opportunity_unit_version_id=NEW.unit_version_id;
        IF EXISTS (SELECT 1 FROM investigation_group_bindings
            WHERE unit_id=NEW.unit_id AND (task_id <> NEW.task_id
                OR source_entity_id <> NEW.source_entity_id))
        THEN RAISE EXCEPTION 'GROUP_SOURCE_IDENTITY_OWNERSHIP_CONFLICT'; END IF;
        SELECT * INTO prior FROM investigation_group_bindings
            WHERE task_id=NEW.task_id AND source_entity_id=NEW.source_entity_id
            ORDER BY sequence DESC LIMIT 1;
        IF b.task_id <> t.task_id OR t.status <> 'APPROVED' OR t.delivery_hash <> b.delivery_hash
            OR b.binding_id IS DISTINCT FROM (SELECT binding_id FROM investigation_bindings
                WHERE task_id=t.task_id ORDER BY sequence DESC LIMIT 1)
            OR bundle.status <> 'FROZEN'
            OR bundle.opportunity_id <> b.opportunity_id
            OR bundle.opportunity_version <> b.opportunity_version
            OR NOT EXISTS (SELECT 1 FROM opportunities WHERE opportunity_id=b.opportunity_id
                AND current_version=b.opportunity_version)
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
            OR NEW.sequence <> COALESCE(prior.sequence,0)+1
            OR (prior.group_binding_id IS NOT NULL AND prior.unit_id <> NEW.unit_id)
        THEN RAISE EXCEPTION 'GROUP_SOURCE_TARGET_INVALID'; END IF;
        SELECT value INTO STRICT raw_group
            FROM jsonb_array_elements(t.delivery->'opportunities'->'units')
            WHERE value->>'id'=NEW.source_entity_id;
        SELECT value INTO STRICT raw_entity
            FROM jsonb_array_elements(t.delivery->'evidence'->'entities')
            WHERE value->>'id'=NEW.source_entity_id AND value->>'kind'='unit';
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'entity_id', p.value->>'id',
            'state', CASE WHEN mapping.value IS NULL THEN 'UNPROCESSED' ELSE 'BOUND' END,
            'position_binding', mapping.value) ORDER BY p.ordinal), '[]'::jsonb) INTO members
        FROM jsonb_array_elements(raw_group->'positions') WITH ORDINALITY p(value,ordinal)
        LEFT JOIN LATERAL (SELECT value FROM jsonb_array_elements(b.request->'positions')
            WHERE value->>'entity_id'=p.value->>'id') mapping ON true;
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(members) m
            WHERE m->>'state'='BOUND' AND NOT EXISTS (
                SELECT 1 FROM opportunity_units child JOIN opportunity_unit_versions cv
                    ON cv.opportunity_unit_version_id=child.current_version_id
                WHERE child.opportunity_unit_id::text=m->'position_binding'->>'opportunity_unit_id'
                    AND cv.opportunity_unit_version_id::text=
                        m->'position_binding'->>'opportunity_unit_version_id'
                    AND child.opportunity_id=b.opportunity_id
                    AND child.opportunity_version=b.opportunity_version
                    AND child.unit_kind='POSITION' AND child.lifecycle_status='ACTIVE'
                    AND cv.opportunity_unit_id=child.opportunity_unit_id AND cv.status='ACTIVE'
            )
        ) THEN RAISE EXCEPTION 'GROUP_SOURCE_MEMBER_INVALID'; END IF;
        expected := jsonb_build_object(
            'contract_version','group-identity/1.0.0', 'scope','GROUP_SOURCE_ASSOCIATION_ONLY',
            'task_id',t.task_id::text, 'delivery_hash',t.delivery_hash,
            'binding_id',b.binding_id::text, 'binding_hash',b.request_hash,
            'opportunity_id',b.opportunity_id::text, 'opportunity_version',b.opportunity_version,
            'source_bundle_revision_id',bundle.source_bundle_revision_id::text,
            'canonical_bundle_hash',bundle.canonical_bundle_hash,
            'source_snapshot_hash',encode(sha256(convert_to(p9b_canonical_json(t.source_snapshot),'UTF8')),'hex'),
            'source_group',raw_group, 'source_entity',raw_entity, 'members',members,
            'membership_status',CASE WHEN jsonb_array_length(members)=0 THEN 'NO_MEMBERS'
                WHEN EXISTS (SELECT 1 FROM jsonb_array_elements(members) m
                    WHERE m->>'state'='UNPROCESSED')
                THEN 'UNPROCESSED_MEMBERS' ELSE 'ALL_MEMBERS_BOUND' END
        );
        IF NEW.source IS DISTINCT FROM expected OR NEW.source_hash IS DISTINCT FROM
            encode(sha256(convert_to(p9b_canonical_json(expected),'UTF8')),'hex')
        THEN RAISE EXCEPTION 'GROUP_SOURCE_CONTENT_INVALID'; END IF;
        group_key := 'group:' || encode(sha256(convert_to(p9b_canonical_json(
            jsonb_build_array(NEW.task_id::text,NEW.source_entity_id)),'UTF8')),'hex');
        IF u.unit_kind <> 'GROUP' OR u.lifecycle_status <> 'ACTIVE'
            OR u.current_version_id IS DISTINCT FROM NEW.unit_version_id
            OR u.current_unit_key <> group_key OR u.normalized_current_unit_key <> group_key
            OR u.opportunity_id <> b.opportunity_id
            OR u.opportunity_version <> b.opportunity_version
            OR v.opportunity_unit_id <> u.opportunity_unit_id
            OR v.opportunity_id <> b.opportunity_id
            OR v.opportunity_version <> b.opportunity_version OR v.status <> 'ACTIVE'
            OR v.source_bundle_revision_id <> b.source_bundle_revision_id
            OR v.canonical_label IS DISTINCT FROM raw_group->>'name'
            OR v.identity_fingerprint IS DISTINCT FROM encode(sha256(convert_to(p9b_canonical_json(
                jsonb_build_object('contract_version','group-identity/1.0.0','group_source_hash',NEW.source_hash)),'UTF8')),'hex')
            OR (prior.group_binding_id IS NOT NULL
                AND v.supersedes_version_id IS DISTINCT FROM prior.unit_version_id)
        THEN RAISE EXCEPTION 'GROUP_SOURCE_IDENTITY_INVALID'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_group_binding_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_group_bindings FOR EACH ROW
        EXECUTE FUNCTION investigation_guard_group_binding();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM investigation_group_bindings)")):
        raise RuntimeError("GROUP_SOURCE_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_group_bindings")
    op.execute("DROP FUNCTION investigation_guard_group_binding()")
