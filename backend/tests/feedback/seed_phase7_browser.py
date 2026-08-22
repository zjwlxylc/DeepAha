from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase4 import MatchSnapshotSchemaV04
from deepaha.core.settings import Settings
from deepaha.eligibility.service import EligibilityService, MatchInput
from deepaha.feedback.models import FeedbackEventModel
from deepaha.opportunities.models import Opportunity
from deepaha.personal.auth import Principal
from deepaha.personal.matching import PersonalMatchService
from deepaha.personal.models import PersonalUserModel, UserStateSnapshotModel
from deepaha.personal.profile import ProfileService
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.review.auth import ReviewerRole
from deepaha.review.models import ReviewerAccountModel
from deepaha.rules.major import load_approved_major_mapping, load_major_catalog
from deepaha.sources.models import Source
from tests.feedback.support import load_phase7_feedback_fixture
from tests.personal.support import (
    FIXTURE_NOW,
    Phase6FixtureIdentity,
    load_phase6_fixture,
    persist_phase6_fixture,
)
from tests.public_catalog.support import stable_uuid7
from tests.review.support import persist_reviewer, reviewer_id

EVALUATION_FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "evaluation"


@dataclass(frozen=True, slots=True)
class Phase7BrowserIdentity:
    user_id: UUID
    personal_session: str
    reviewer_id: UUID
    reviewer_session: str
    public_ids: tuple[str, ...]
    initial_public_id: str


class SyntheticFixtureEligibilityService(EligibilityService):
    def evaluate_personal_and_save(
        self,
        match_input: MatchInput,
    ) -> MatchSnapshotSchemaV04:
        return self.evaluate_and_save(match_input)


def assert_phase7_browser_database_url(database_url: str) -> None:
    url = make_url(database_url)
    if url.host != "127.0.0.1" or url.port != 55437 or url.database != "deepaha":
        raise ValueError("browser seed requires exact disposable database 127.0.0.1:55437/deepaha")


def _persist_synthetic_profile(session: Session, identity: Phase6FixtureIdentity) -> None:
    fixture_user = load_phase6_fixture().users[0]
    if fixture_user.user_id != identity.user_a_id:
        raise ValueError("Phase 7 browser user does not match the fixed Phase 6 fixture")
    profile = fixture_user.profile
    profile_snapshot_id = stable_uuid7("phase7:browser:profile")
    state_snapshot_id = stable_uuid7("phase7:browser:user-state")
    attributes = profile.attributes.model_dump(mode="json")
    attributes["target_regions"] = list(profile.preference_regions)
    attributes["certificates"] = []
    skipped_fields = [
        value.value
        for value in profile.skipped_fields
        if value.value not in {"target_regions", "certificates"}
    ]
    session.add(
        ProfileSnapshotModel(
            profile_snapshot_id=profile_snapshot_id,
            profile_id=fixture_user.user_state_id,
            version=1,
            synthetic=True,
            persona_family_id=None,
            attributes=attributes,
            scenario_clock=profile.scenario_clock,
            profile_schema_version="0.4.0",
            created_at=FIXTURE_NOW,
            created_by="phase7-browser-fixture",
            reviewed_by="phase7-fixture-governance",
            change_note="Synthetic browser profile; not a human participant.",
        )
    )
    session.flush()
    state_input = {
        "user_id": str(fixture_user.user_id),
        "profile_snapshot_id": str(profile_snapshot_id),
        "attributes": attributes,
        "skipped_fields": skipped_fields,
    }
    session.add(
        UserStateSnapshotModel(
            user_state_snapshot_id=state_snapshot_id,
            user_state_id=fixture_user.user_state_id,
            user_id=fixture_user.user_id,
            version=1,
            qualification_profile_snapshot_id=profile_snapshot_id,
            qualification_profile_version=1,
            life_stage=None if profile.life_stage is None else profile.life_stage.value,
            goal_types=[value.value for value in profile.goal_types],
            preference_regions=list(profile.preference_regions),
            preference_types=[value.value for value in profile.preference_types],
            skipped_fields=skipped_fields,
            personalization_enabled=profile.personalization_enabled,
            consent_version=profile.consent_version,
            allowed_purposes=[value.value for value in profile.allowed_purposes],
            scenario_clock=profile.scenario_clock,
            input_sha256=sha256(
                json.dumps(state_input, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            created_at=FIXTURE_NOW,
        )
    )
    session.flush()


def _run_synthetic_matches(
    factory: sessionmaker[Session],
    identity: Phase6FixtureIdentity,
) -> str:
    catalog = load_major_catalog(EVALUATION_FIXTURE_ROOT / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(
        EVALUATION_FIXTURE_ROOT / "phase4-major-mapping.json",
        catalog,
    )
    profile = ProfileService(
        session_factory=factory,
        now_factory=lambda: FIXTURE_NOW,
        allow_synthetic_fixture_profile=True,
    )
    matching = PersonalMatchService(
        session_factory=factory,
        profile_service=profile,
        eligibility_service=SyntheticFixtureEligibilityService(session_factory=factory),
        major_catalog=catalog,
        major_mapping=mapping,
        now_factory=lambda: FIXTURE_NOW,
    )
    ranking = matching.run(Principal(user_id=identity.user_a_id))
    if not ranking.items:
        raise ValueError("Phase 7 browser fixture produced no personal opportunity")
    with factory() as session:
        opportunity = session.get(Opportunity, ranking.items[0].opportunity_id)
        if opportunity is None:
            raise ValueError("Phase 7 browser opportunity is missing")
        return opportunity.public_id


def seed_phase7_browser(database_url: str) -> Phase7BrowserIdentity:
    assert_phase7_browser_database_url(database_url)
    load_phase7_feedback_fixture()
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            counts = {
                "personal_users": session.scalar(
                    select(func.count()).select_from(PersonalUserModel)
                ),
                "reviewers": session.scalar(select(func.count()).select_from(ReviewerAccountModel)),
                "sources": session.scalar(select(func.count()).select_from(Source)),
                "opportunities": session.scalar(select(func.count()).select_from(Opportunity)),
                "feedback_events": session.scalar(
                    select(func.count()).select_from(FeedbackEventModel)
                ),
            }
            if any(counts.values()):
                raise RuntimeError("browser seed requires an empty Phase 7 fixture scope")
            identity = persist_phase6_fixture(session)
            _persist_synthetic_profile(session, identity)
            reviewer_session = token_urlsafe(32)
            persist_reviewer(
                session,
                index=10,
                token=reviewer_session,
                roles=tuple(ReviewerRole),
            )
            session.commit()
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        initial_public_id = _run_synthetic_matches(factory, identity)
        return Phase7BrowserIdentity(
            user_id=identity.user_a_id,
            personal_session=identity.token_a,
            reviewer_id=reviewer_id(10),
            reviewer_session=reviewer_session,
            public_ids=identity.public_ids,
            initial_public_id=initial_public_id,
        )
    finally:
        engine.dispose()


def main() -> None:
    database_url = Settings().database_url
    if database_url is None:
        raise ValueError("DEEPAHA_DATABASE_URL is required")
    identity = seed_phase7_browser(database_url)
    print("SYNTHETIC_FEEDBACK_WORKFLOW_ONLY")
    print("real participants=0")
    print("human track=NOT_STARTED")
    print("Release Qualification=NOT_STARTED")
    print("release decision=HOLD_MISSING_HUMAN_EVIDENCE")
    print(f"personal_session_cookie={identity.personal_session}")
    print(f"reviewer_session_cookie={identity.reviewer_session}")
    print(f"initial_public_id={identity.initial_public_id}")


if __name__ == "__main__":
    main()
