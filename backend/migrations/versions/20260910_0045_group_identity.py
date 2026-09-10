"""Independent internal group identity, isolated from legacy unit lineage."""

import sqlalchemy as sa
from alembic import op

revision = "20260910_0045"
down_revision = "20260909_0044"
branch_labels = None
depends_on = None

LEGACY_KINDS = "'POSITION', 'TRACK', 'PROGRAM_TIER', 'REGION_VARIANT', 'DEFAULT_SINGLETON'"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_opportunity_units_kind_values"), "opportunity_units", type_="check")
    op.create_check_constraint(
        op.f("ck_opportunity_units_kind_values"),
        "opportunity_units",
        f"unit_kind in ({LEGACY_KINDS}, 'GROUP')",
    )
    op.execute("""
    CREATE FUNCTION p9b_guard_group_kind() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.unit_kind IS DISTINCT FROM NEW.unit_kind
           AND (OLD.unit_kind = 'GROUP' OR NEW.unit_kind = 'GROUP') THEN
            RAISE EXCEPTION 'GROUP_KIND_IMMUTABLE';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER opportunity_units_guard_group_kind BEFORE UPDATE ON opportunity_units
        FOR EACH ROW EXECUTE FUNCTION p9b_guard_group_kind();
    """)
    # Require the exact immutable version to exist before accepting a legacy member.
    # A negative GROUP lookup alone would allow a missing parent inserted later in a CTE.
    op.execute(f"""
    CREATE FUNCTION p9b_guard_group_lineage() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM opportunity_unit_versions v
            JOIN opportunity_units u ON u.opportunity_unit_id = v.opportunity_unit_id
            WHERE v.opportunity_unit_id = NEW.opportunity_unit_id
              AND v.opportunity_unit_version_id = NEW.opportunity_unit_version_id
              AND v.opportunity_id = NEW.opportunity_id
              AND u.opportunity_id = NEW.opportunity_id
              AND u.unit_kind IN ({LEGACY_KINDS})
        ) THEN
            RAISE EXCEPTION 'GROUP_LEGACY_LINEAGE_FORBIDDEN_OR_IDENTITY_MISSING';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER opportunity_unit_lineage_guard_group BEFORE INSERT
        ON opportunity_unit_lineage_members FOR EACH ROW
        EXECUTE FUNCTION p9b_guard_group_lineage();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM opportunity_units WHERE unit_kind='GROUP')")
    ):
        raise RuntimeError("GROUP_IDENTITY_HISTORY_DOWNGRADE_REFUSED")
    op.execute(
        "DROP TRIGGER opportunity_unit_lineage_guard_group ON opportunity_unit_lineage_members"
    )
    op.execute("DROP FUNCTION p9b_guard_group_lineage()")
    op.execute("DROP TRIGGER opportunity_units_guard_group_kind ON opportunity_units")
    op.execute("DROP FUNCTION p9b_guard_group_kind()")
    op.drop_constraint(op.f("ck_opportunity_units_kind_values"), "opportunity_units", type_="check")
    op.create_check_constraint(
        op.f("ck_opportunity_units_kind_values"),
        "opportunity_units",
        f"unit_kind in ({LEGACY_KINDS})",
    )
