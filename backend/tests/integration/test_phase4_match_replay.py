from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.eligibility.models import EligibilityResultModel
from deepaha.eligibility.service import (
    EligibilityService,
    MatchInput,
    MatchInputError,
)
from deepaha.matching.models import MatchSnapshotModel
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.rules.major import (
    ApprovedMajorMapping,
    MajorCatalog,
    load_approved_major_mapping,
    load_major_catalog,
)
from tests.integration.test_phase4_persistence_contract import persist_phase4_inputs

pytestmark = pytest.mark.integration
FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "evaluation"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def major_assets() -> tuple[MajorCatalog, ApprovedMajorMapping]:
    catalog = load_major_catalog(FIXTURE_DIRECTORY / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(
        FIXTURE_DIRECTORY / "phase4-major-mapping.json",
        catalog,
    )
    return catalog, mapping


@pytest.fixture
def phase4_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(migrated_engine, expire_on_commit=False)


@pytest.fixture
def seeded_identity(
    phase4_session_factory: sessionmaker[Session],
) -> tuple[UUID, int, UUID, int, UUID]:
    with phase4_session_factory() as session:
        rule_set, profile, _, _ = persist_phase4_inputs(session)
        session.commit()
        return (
            rule_set.opportunity_id,
            rule_set.opportunity_version,
            rule_set.rule_set_id,
            rule_set.version,
            profile.profile_snapshot_id,
        )


@pytest.fixture
def service(phase4_session_factory: sessionmaker[Session]) -> EligibilityService:
    return EligibilityService(session_factory=phase4_session_factory, id_factory=uuid7)


def match_input(
    seeded_identity: tuple[UUID, int, UUID, int, UUID],
    major_assets: tuple[MajorCatalog, ApprovedMajorMapping],
    *,
    profile_snapshot_id: UUID | None = None,
    catalog: MajorCatalog | None = None,
    mapping: ApprovedMajorMapping | None = None,
    evaluated_at: datetime = NOW,
    created_at: datetime = NOW,
) -> MatchInput:
    opportunity_id, opportunity_version, rule_set_id, rule_set_version, profile_id = seeded_identity
    default_catalog, default_mapping = major_assets
    return MatchInput(
        opportunity_id=opportunity_id,
        opportunity_version=opportunity_version,
        rule_set_id=rule_set_id,
        rule_set_version=rule_set_version,
        profile_snapshot_id=profile_snapshot_id or profile_id,
        major_catalog=catalog or default_catalog,
        major_mapping=mapping or default_mapping,
        evaluated_at=evaluated_at,
        created_at=created_at,
    )


def test_same_input_returns_same_match_snapshot_without_duplicate_result(
    service: EligibilityService,
    phase4_session_factory: sessionmaker[Session],
    seeded_identity: tuple[UUID, int, UUID, int, UUID],
    major_assets: tuple[MajorCatalog, ApprovedMajorMapping],
) -> None:
    first = service.evaluate_and_save(match_input(seeded_identity, major_assets))
    second = service.evaluate_and_save(
        match_input(
            seeded_identity,
            major_assets,
            evaluated_at=NOW + timedelta(hours=1),
            created_at=NOW + timedelta(hours=1),
        )
    )
    assert second == first
    assert second.snapshot_id == first.snapshot_id
    assert second.input_sha256 == first.input_sha256
    assert second.profile_version == 1
    with phase4_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MatchSnapshotModel)) == 1
        assert session.scalar(select(func.count()).select_from(EligibilityResultModel)) == 1


def test_replay_reconstructs_saved_snapshot_without_current_config_substitution(
    service: EligibilityService,
    seeded_identity: tuple[UUID, int, UUID, int, UUID],
    major_assets: tuple[MajorCatalog, ApprovedMajorMapping],
) -> None:
    saved = service.evaluate_and_save(match_input(seeded_identity, major_assets))
    replayed = service.replay(saved.snapshot_id)
    assert replayed.model_dump(mode="json") == saved.model_dump(mode="json")


def test_profile_and_scenario_version_change_produces_explainable_diff(
    service: EligibilityService,
    phase4_session_factory: sessionmaker[Session],
    seeded_identity: tuple[UUID, int, UUID, int, UUID],
    major_assets: tuple[MajorCatalog, ApprovedMajorMapping],
) -> None:
    first = service.evaluate_and_save(match_input(seeded_identity, major_assets))
    original_snapshot_id = seeded_identity[-1]
    with phase4_session_factory() as session:
        original = session.get(ProfileSnapshotModel, original_snapshot_id)
        assert original is not None
        replacement = ProfileSnapshotModel(
            profile_snapshot_id=uuid7(),
            profile_id=original.profile_id,
            version=2,
            synthetic=True,
            persona_family_id=original.persona_family_id,
            attributes=original.attributes | {"education_level": "MASTER"},
            scenario_clock=original.scenario_clock + timedelta(days=1),
            profile_schema_version=original.profile_schema_version,
            created_at=NOW + timedelta(days=1),
            created_by=original.created_by,
            reviewed_by=original.reviewed_by,
            change_note="Synthetic counterfactual profile version",
        )
        session.add(replacement)
        session.commit()
        replacement_id = replacement.profile_snapshot_id
    second = service.evaluate_and_save(
        match_input(
            seeded_identity,
            major_assets,
            profile_snapshot_id=replacement_id,
            evaluated_at=NOW + timedelta(days=1),
            created_at=NOW + timedelta(days=1),
        )
    )
    assert second.snapshot_id != first.snapshot_id
    assert second.input_sha256 != first.input_sha256
    assert second.profile_version == 2
    differences = {item.field for item in service.diff(first.snapshot_id, second.snapshot_id)}
    assert {"profile_snapshot_id", "profile_version", "scenario_clock"} <= differences


def test_catalog_and_mapping_version_change_is_in_the_input_and_diff(
    service: EligibilityService,
    seeded_identity: tuple[UUID, int, UUID, int, UUID],
    major_assets: tuple[MajorCatalog, ApprovedMajorMapping],
) -> None:
    first = service.evaluate_and_save(match_input(seeded_identity, major_assets))
    catalog, mapping = major_assets
    catalog_v2 = replace(catalog, version="phase4-synthetic-major-catalog-v2")
    mapping_v2 = replace(
        mapping,
        version="phase4-synthetic-major-mapping-v2",
        catalog_version=catalog_v2.version,
    )
    second = service.evaluate_and_save(
        match_input(
            seeded_identity,
            major_assets,
            catalog=catalog_v2,
            mapping=mapping_v2,
        )
    )
    assert second.input_sha256 != first.input_sha256
    differences = {item.field for item in service.diff(first.snapshot_id, second.snapshot_id)}
    assert {"major_catalog_version", "major_mapping_version"} <= differences


def test_missing_exact_input_rejects_without_persisting_snapshot(
    service: EligibilityService,
    phase4_session_factory: sessionmaker[Session],
    seeded_identity: tuple[UUID, int, UUID, int, UUID],
    major_assets: tuple[MajorCatalog, ApprovedMajorMapping],
) -> None:
    invalid = match_input(seeded_identity, major_assets)
    invalid = replace(invalid, opportunity_version=999)
    with pytest.raises(MatchInputError, match="OpportunityVersion"):
        service.evaluate_and_save(invalid)
    with phase4_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MatchSnapshotModel)) == 0
