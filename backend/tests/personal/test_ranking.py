from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from deepaha.contracts.phase1 import OpportunityStatus
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase4 import EligibilityStatus
from deepaha.contracts.phase6 import RankingReasonCode, UserStateSnapshotSchemaV05
from deepaha.personal.matching import RankableMatch, rank_personal_matches

TODAY = date(2026, 8, 22)
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


def state_values(**changes: object) -> UserStateSnapshotSchemaV05:
    values: dict[str, object] = {
        "user_state_snapshot_id": UUID("019b0000-0000-7000-8000-000000000601"),
        "user_state_id": UUID("019b0000-0000-7000-8000-000000000602"),
        "version": 1,
        "qualification_profile_snapshot_id": UUID("019b0000-0000-7000-8000-000000000603"),
        "qualification_profile_version": 1,
        "life_stage": "GRADUATING",
        "goal_types": ["PUBLIC_SERVICE_EMPLOYMENT"],
        "attributes": {
            "education_level": "BACHELOR",
            "major_name": None,
            "major_code": None,
            "graduation_year": 2026,
            "student_status": "GRADUATING",
            "birth_date": None,
            "hukou_region": None,
            "residence_region": "合成杭州市",
            "target_regions": None,
            "certificates": None,
        },
        "preference_regions": ["合成杭州市"],
        "preference_types": ["PUBLIC_INSTITUTION_JOB"],
        "skipped_fields": [
            "birth_date",
            "certificates",
            "hukou_region",
            "major_code",
            "major_name",
            "target_regions",
        ],
        "personalization_enabled": True,
        "consent_version": "phase6-consent-v1",
        "allowed_purposes": ["ACTION_TRACKING", "ELIGIBILITY", "PERSONAL_RANKING"],
        "scenario_clock": TODAY,
        "input_sha256": "1" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return UserStateSnapshotSchemaV05.model_validate(values)


def match(
    index: int,
    *,
    eligibility_status: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    opportunity_type: OpportunityTypeV02 = OpportunityTypeV02.PUBLIC_INSTITUTION_JOB,
    locations: tuple[str, ...] = ("合成杭州市",),
    public_status: OpportunityStatus = OpportunityStatus.OPEN,
    deadline: date | None = None,
) -> RankableMatch:
    return RankableMatch(
        public_id=f"opp_{index:032x}",
        opportunity_id=UUID(f"019b0000-0000-7000-8000-{700 + index:012d}"),
        opportunity_version=1,
        match_snapshot_id=UUID(f"019b0000-0000-7000-8000-{800 + index:012d}"),
        eligibility_status=eligibility_status,
        opportunity_type=opportunity_type,
        locations=locations,
        public_status=public_status,
        deadline=deadline or TODAY + timedelta(days=index),
    )


def test_ranking_enforces_public_status_inclusive_ninety_days_and_max_three() -> None:
    ranked = rank_personal_matches(
        (
            match(1, deadline=TODAY),
            match(2, eligibility_status=EligibilityStatus.LIKELY_ELIGIBLE),
            match(
                3,
                eligibility_status=EligibilityStatus.UNCERTAIN,
                deadline=TODAY + timedelta(days=90),
            ),
            match(4, eligibility_status=EligibilityStatus.INELIGIBLE),
            match(5, public_status=OpportunityStatus.CLOSED),
            match(6, deadline=TODAY + timedelta(days=91)),
        ),
        state_values(),
    )

    assert [item.opportunity_id for item in ranked] == [
        match(1).opportunity_id,
        match(2).opportunity_id,
        match(3).opportunity_id,
    ]
    assert [item.ordinal for item in ranked] == [1, 2, 3]


def test_soft_preference_changes_order_but_not_status_or_match_identity() -> None:
    hangzhou = match(
        1,
        locations=("合成杭州市",),
        opportunity_type=OpportunityTypeV02.YOUTH_POLICY_BENEFIT,
    )
    ningbo = match(
        2,
        locations=("合成宁波市",),
        opportunity_type=OpportunityTypeV02.PUBLIC_INSTITUTION_JOB,
    )

    first = rank_personal_matches((hangzhou, ningbo), state_values())
    changed_state = state_values(
        preference_regions=["合成宁波市"],
        preference_types=["PUBLIC_INSTITUTION_JOB"],
        input_sha256="2" * 64,
    )
    second = rank_personal_matches((hangzhou, ningbo), changed_state)

    assert [item.opportunity_id for item in first] == [
        hangzhou.opportunity_id,
        ningbo.opportunity_id,
    ]
    assert [item.opportunity_id for item in second] == [
        ningbo.opportunity_id,
        hangzhou.opportunity_id,
    ]
    assert {item.opportunity_id: item.eligibility_status for item in first} == {
        item.opportunity_id: item.eligibility_status for item in second
    }
    assert {item.opportunity_id: item.match_snapshot_id for item in first} == {
        item.opportunity_id: item.match_snapshot_id for item in second
    }


@pytest.mark.parametrize(
    "status",
    [
        OpportunityStatus.CANCELLED,
        OpportunityStatus.SUPERSEDED,
        OpportunityStatus.UNKNOWN,
    ],
)
def test_non_actionable_public_statuses_never_enter_ranking(
    status: OpportunityStatus,
) -> None:
    assert rank_personal_matches((match(1, public_status=status),), state_values()) == ()


def test_disabled_personalization_ignores_soft_preferences() -> None:
    preferred_but_later = match(2, deadline=TODAY + timedelta(days=2))
    earlier = match(
        1,
        deadline=TODAY + timedelta(days=1),
        locations=("合成宁波市",),
        opportunity_type=OpportunityTypeV02.YOUTH_POLICY_BENEFIT,
    )

    ranked = rank_personal_matches(
        (preferred_but_later, earlier),
        state_values(personalization_enabled=False),
    )

    assert [item.opportunity_id for item in ranked] == [
        earlier.opportunity_id,
        preferred_but_later.opportunity_id,
    ]
    assert all(
        RankingReasonCode.PREFERRED_REGION not in item.reason_codes
        and RankingReasonCode.PREFERRED_TYPE not in item.reason_codes
        for item in ranked
    )
