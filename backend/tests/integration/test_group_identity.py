from datetime import timedelta
from uuid import uuid7

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.p9b.identity import OpportunityUnitService, UnitIdentityError, UnitSeed
from deepaha.p9b.models import OpportunityUnit, OpportunityUnitLineageEvent, OpportunityUnitVersion

from .test_p9b_b0_persistence import NOW, frozen_bundle, seed_graph

pytestmark = pytest.mark.integration


def test_group_has_independent_stable_identity_and_version(session: Session) -> None:
    graph = seed_graph(session)
    bundle = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    units = [
        service.create_unit(
            opportunity_id=graph.opportunity_id,
            opportunity_version=1,
            source_bundle_revision_id=bundle.source_bundle_revision_id,
            seed=UnitSeed(key, kind, "Same display label", "a" * 64),
            effective_from=NOW,
        )
        for key, kind in (("group:01", "GROUP"), ("01", "POSITION"))
    ]
    group, position = units
    original_id = group.opportunity_unit_id
    prior = group.current_version_id
    version = service.append_version_cas(
        opportunity_unit_id=original_id,
        expected_current_version_id=prior,
        opportunity_version=1,
        source_bundle_revision_id=bundle.source_bundle_revision_id,
        effective_from=NOW + timedelta(minutes=1),
        canonical_label="Updated group label",
        identity_fingerprint="b" * 64,
    )
    session.flush()
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert group.unit_kind == "GROUP"
    assert group.opportunity_unit_id == original_id != position.opportunity_unit_id
    assert group.current_version_id == version.opportunity_unit_version_id != prior
    assert version.source_bundle_revision_id == bundle.source_bundle_revision_id
    assert position.unit_kind == "POSITION"


@pytest.mark.parametrize("source_kind,target_kind", [("GROUP", "POSITION"), ("POSITION", "GROUP")])
@pytest.mark.parametrize("reversal", [False, True])
def test_group_cannot_participate_in_legacy_merge(
    session: Session, source_kind: str, target_kind: str, reversal: bool
) -> None:
    graph = seed_graph(session)
    bundle = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    units = [
        service.create_unit(
            opportunity_id=graph.opportunity_id,
            opportunity_version=1,
            source_bundle_revision_id=bundle.source_bundle_revision_id,
            seed=UnitSeed(key, kind, key, "a" * 64),
            effective_from=NOW,
        )
        for key, kind in (("source", source_kind), ("position", "POSITION"))
    ]
    pointers = [unit.current_version_id for unit in units]
    with pytest.raises(UnitIdentityError, match="GROUP.*lineage"):
        service.merge_units(
            opportunity_unit_ids=[unit.opportunity_unit_id for unit in units],
            source_bundle_revision_id=bundle.source_bundle_revision_id,
            evidence_ref_ids=[graph.evidence_ref_id],
            target=UnitSeed("target", target_kind, "Target", "b" * 64),
            effective_at=NOW + timedelta(hours=1),
            reason_code="SYNTHETIC_TEST",
            actor_identity="synthetic-reviewer",
            reverses_split_event_id=graph.evidence_ref_id if reversal else None,
        )
    assert [unit.current_version_id for unit in units] == pointers
    assert all(unit.lifecycle_status == "ACTIVE" for unit in units)
    assert session.scalar(select(func.count()).select_from(OpportunityUnitLineageEvent)) == 0
    assert session.scalar(select(func.count()).select_from(OpportunityUnitVersion)) == 2


def test_singleton_cannot_split_into_group(session: Session) -> None:
    graph = seed_graph(session)
    bundle = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    unit = service.create_default_singleton(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=bundle.source_bundle_revision_id,
        effective_from=NOW,
        canonical_label="Singleton",
        identity_fingerprint="a" * 64,
    )
    with pytest.raises(UnitIdentityError, match="GROUP.*lineage"):
        service.split_singleton(
            opportunity_unit_id=unit.opportunity_unit_id,
            expected_current_version_id=unit.current_version_id,
            source_bundle_revision_id=bundle.source_bundle_revision_id,
            evidence_ref_ids=[graph.evidence_ref_id],
            units=[
                UnitSeed("group:01", "GROUP", "Group", "b" * 64),
                UnitSeed("01", "POSITION", "Position", "c" * 64),
            ],
            effective_at=NOW + timedelta(hours=1),
            reason_code="SYNTHETIC_TEST",
            actor_identity="synthetic-reviewer",
        )
    assert unit.lifecycle_status == "ACTIVE"
    assert session.scalar(select(func.count()).select_from(OpportunityUnit)) == 1


def test_group_rekey_rejected_before_any_mutation(session: Session) -> None:
    graph = seed_graph(session)
    bundle = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    group = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=bundle.source_bundle_revision_id,
        seed=UnitSeed("group:01", "GROUP", "Group", "a" * 64),
        effective_from=NOW,
    )
    prior = group.current_version_id
    with pytest.raises(UnitIdentityError, match="GROUP.*lineage"):
        service.rekey_unit(
            opportunity_unit_id=group.opportunity_unit_id,
            new_key="group:02",
            source_bundle_revision_id=bundle.source_bundle_revision_id,
            evidence_ref_ids=[graph.evidence_ref_id],
            confidence="DETERMINISTIC",
            effective_at=NOW + timedelta(hours=1),
            reason_code="SYNTHETIC_TEST",
            actor_identity="synthetic-reviewer",
        )
    assert group.current_version_id == prior
    assert group.current_unit_key == "group:01"


@pytest.mark.parametrize(
    "source_kind,target_kind",
    [
        pair
        for kind in ("POSITION", "TRACK", "PROGRAM_TIER", "REGION_VARIANT", "DEFAULT_SINGLETON")
        for pair in (("GROUP", kind), (kind, "GROUP"))
    ],
)
def test_sql_cannot_convert_group_kind(
    session: Session, source_kind: str, target_kind: str
) -> None:
    graph = seed_graph(session)
    bundle = frozen_bundle(session, graph)
    unit = OpportunityUnitService(session).create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=bundle.source_bundle_revision_id,
        seed=UnitSeed("01", source_kind, "Unit", "a" * 64),
        effective_from=NOW,
    )
    with pytest.raises(DBAPIError, match="GROUP_KIND_IMMUTABLE"):
        session.execute(
            text("UPDATE opportunity_units SET unit_kind=:kind WHERE opportunity_unit_id=:id"),
            {"kind": target_kind, "id": unit.opportunity_unit_id},
        )


@pytest.mark.parametrize("role", ["SOURCE", "TARGET"])
def test_sql_cannot_add_group_to_legacy_lineage(session: Session, role: str) -> None:
    graph = seed_graph(session)
    bundle = frozen_bundle(session, graph)
    group = OpportunityUnitService(session).create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=bundle.source_bundle_revision_id,
        seed=UnitSeed("group:01", "GROUP", "Group", "a" * 64),
        effective_from=NOW,
    )
    session.execute(
        text(
            "INSERT INTO opportunity_unit_lineage_events "
            "(lineage_event_id,opportunity_id,event_type,source_bundle_revision_id,"
            "reason_code,actor_identity,created_at) VALUES "
            "(:event,:opp,'MERGE',:bundle,'SYNTHETIC_TEST','synthetic-reviewer',:now)"
        ),
        {
            "event": graph.evidence_ref_id,
            "opp": graph.opportunity_id,
            "bundle": bundle.source_bundle_revision_id,
            "now": NOW,
        },
    )
    with pytest.raises(DBAPIError, match="GROUP_LEGACY_LINEAGE_FORBIDDEN"):
        session.execute(
            text(
                "INSERT INTO opportunity_unit_lineage_members "
                "(lineage_event_id,opportunity_id,member_role,opportunity_unit_id,"
                "opportunity_unit_version_id) VALUES (:event,:opp,:role,:unit,:version)"
            ),
            {
                "event": graph.evidence_ref_id,
                "opp": graph.opportunity_id,
                "role": role,
                "unit": group.opportunity_unit_id,
                "version": group.current_version_id,
            },
        )


def test_sql_member_before_parent_cte_fails_closed(session: Session) -> None:
    graph = seed_graph(session)
    bundle = frozen_bundle(session, graph)
    position = OpportunityUnitService(session).create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=bundle.source_bundle_revision_id,
        seed=UnitSeed("01", "POSITION", "Position", "a" * 64),
        effective_from=NOW,
    )
    session.execute(
        text(
            "INSERT INTO opportunity_unit_lineage_events "
            "(lineage_event_id,opportunity_id,event_type,source_bundle_revision_id,"
            "reason_code,actor_identity,created_at) VALUES "
            "(:event,:opp,'MERGE',:bundle,'SYNTHETIC_TEST','synthetic-reviewer',:now)"
        ),
        {
            "event": graph.evidence_ref_id,
            "opp": graph.opportunity_id,
            "bundle": bundle.source_bundle_revision_id,
            "now": NOW,
        },
    )
    group_id, version_id = uuid7(), uuid7()
    with pytest.raises(DBAPIError, match="GROUP_LEGACY_LINEAGE_FORBIDDEN_OR_IDENTITY_MISSING"):
        session.execute(
            text("""
            WITH member AS (
                INSERT INTO opportunity_unit_lineage_members
                    (lineage_event_id, opportunity_id, member_role,
                     opportunity_unit_id, opportunity_unit_version_id)
                VALUES (:event, :opp, 'TARGET', :group, :version)
                RETURNING opportunity_unit_id
            ), new_group AS (
                INSERT INTO opportunity_units
                    (opportunity_unit_id, public_id, opportunity_id, opportunity_version,
                     current_unit_key, normalized_current_unit_key, unit_kind,
                     lifecycle_status, current_version_id, created_at, retired_at)
                SELECT m.opportunity_unit_id, :public_id, :opp, 1,
                       'group:01', 'group:01', 'GROUP', 'ACTIVE', NULL, :now, NULL
                FROM member m RETURNING opportunity_unit_id
            )
            INSERT INTO opportunity_unit_versions
                (opportunity_unit_version_id, opportunity_unit_id, opportunity_id,
                 opportunity_version, version, source_bundle_revision_id, effective_from,
                 effective_to, status, canonical_label, identity_fingerprint,
                 supersedes_version_id, created_at)
            SELECT :version, g.opportunity_unit_id, v.opportunity_id,
                   v.opportunity_version, 1, v.source_bundle_revision_id, v.effective_from,
                   NULL, 'ACTIVE', 'Group', v.identity_fingerprint, NULL, v.created_at
            FROM opportunity_unit_versions v CROSS JOIN new_group g
            WHERE v.opportunity_unit_version_id = :position_version
        """),
            {
                "event": graph.evidence_ref_id,
                "opp": graph.opportunity_id,
                "group": group_id,
                "version": version_id,
                "public_id": f"unit_{group_id.hex}",
                "now": NOW,
                "position_version": position.current_version_id,
            },
        )
