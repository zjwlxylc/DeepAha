import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase1 import OpportunityStatus
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase4 import EligibilityStatus
from deepaha.contracts.phase6 import (
    PersonalRankingItemSchemaV05,
    PersonalRankingSnapshotSchemaV05,
    RankingReasonCode,
    UserDataPurpose,
    UserStateSnapshotSchemaV05,
)
from deepaha.eligibility.service import EligibilityService, MatchInput
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.personal.auth import Principal
from deepaha.personal.models import (
    PersonalRankingItemModel,
    PersonalRankingSnapshotModel,
    UserStateSnapshotModel,
)
from deepaha.personal.profile import ProfileService
from deepaha.public_catalog.models import PublicCatalogEntry
from deepaha.rules.major import ApprovedMajorMapping, MajorCatalog
from deepaha.rules.models import RuleSetModel

RANKER_VERSION = "phase6-deterministic-ranker-v1"

_ELIGIBILITY_BAND = {
    EligibilityStatus.ELIGIBLE: 0,
    EligibilityStatus.LIKELY_ELIGIBLE: 1,
    EligibilityStatus.UNCERTAIN: 2,
}
_ELIGIBILITY_REASON = {
    EligibilityStatus.ELIGIBLE: RankingReasonCode.ELIGIBILITY_ELIGIBLE,
    EligibilityStatus.LIKELY_ELIGIBLE: RankingReasonCode.ELIGIBILITY_LIKELY,
    EligibilityStatus.UNCERTAIN: RankingReasonCode.ELIGIBILITY_UNCERTAIN,
}


@dataclass(frozen=True, slots=True)
class RankableMatch:
    public_id: str
    opportunity_id: UUID
    opportunity_version: int
    match_snapshot_id: UUID
    eligibility_status: EligibilityStatus
    opportunity_type: OpportunityTypeV02
    locations: tuple[str, ...]
    public_status: OpportunityStatus
    deadline: date


class PersonalMatchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _PublicCandidate:
    public_id: str
    opportunity_id: UUID
    opportunity_version: int
    opportunity_type: OpportunityTypeV02
    locations: tuple[str, ...]
    public_status: OpportunityStatus
    deadline: date


def rank_personal_matches(
    matches: tuple[RankableMatch, ...],
    state: UserStateSnapshotSchemaV05,
) -> tuple[PersonalRankingItemSchemaV05, ...]:
    window_end = state.scenario_clock + timedelta(days=90)
    candidates = tuple(
        item
        for item in matches
        if item.eligibility_status in _ELIGIBILITY_BAND
        and item.public_status in {OpportunityStatus.OPEN, OpportunityStatus.CLOSING_SOON}
        and state.scenario_clock <= item.deadline <= window_end
    )

    def preference_values(item: RankableMatch) -> tuple[bool, bool]:
        if not state.personalization_enabled:
            return False, False
        region_match = bool(set(item.locations) & set(state.preference_regions))
        type_match = item.opportunity_type in state.preference_types
        return region_match, type_match

    ordered = sorted(
        candidates,
        key=lambda item: (
            _ELIGIBILITY_BAND[item.eligibility_status],
            -int(preference_values(item)[0]),
            -int(preference_values(item)[1]),
            item.deadline,
            item.public_id,
        ),
    )
    result: list[PersonalRankingItemSchemaV05] = []
    for ordinal, item in enumerate(ordered[:3], start=1):
        region_match, type_match = preference_values(item)
        reasons = [_ELIGIBILITY_REASON[item.eligibility_status]]
        if region_match:
            reasons.append(RankingReasonCode.PREFERRED_REGION)
        if type_match:
            reasons.append(RankingReasonCode.PREFERRED_TYPE)
        reasons.extend((RankingReasonCode.EARLIER_DEADLINE, RankingReasonCode.STABLE_ID_TIE_BREAK))
        result.append(
            PersonalRankingItemSchemaV05(
                ordinal=ordinal,
                opportunity_id=item.opportunity_id,
                opportunity_version=item.opportunity_version,
                match_snapshot_id=item.match_snapshot_id,
                eligibility_status=item.eligibility_status,
                reason_codes=tuple(reasons),
                deadline=item.deadline,
            )
        )
    return tuple(result)


class PersonalMatchService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        profile_service: ProfileService,
        eligibility_service: EligibilityService,
        major_catalog: MajorCatalog,
        major_mapping: ApprovedMajorMapping,
        id_factory: Callable[[], UUID] = uuid7,
        now_factory: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._profile_service = profile_service
        self._eligibility_service = eligibility_service
        self._major_catalog = major_catalog
        self._major_mapping = major_mapping
        self._id_factory = id_factory
        self._now_factory = now_factory

    def run(self, principal: Principal) -> PersonalRankingSnapshotSchemaV05:
        state = self._profile_service.get_current(principal)
        if state is None or UserDataPurpose.PERSONAL_RANKING not in state.allowed_purposes:
            raise PersonalMatchError("personal matching unavailable")
        candidates = self._load_public_candidates(state)
        created_at = self._now_factory()
        rankable: list[RankableMatch] = []
        match_inputs: list[dict[str, object]] = []
        omitted: list[tuple[UUID, int]] = []
        for candidate in candidates:
            rule_set = self._rule_set_for(candidate)
            if rule_set is None:
                omitted.append((candidate.opportunity_id, candidate.opportunity_version))
                continue
            match = self._eligibility_service.evaluate_personal_and_save(
                MatchInput(
                    opportunity_id=candidate.opportunity_id,
                    opportunity_version=candidate.opportunity_version,
                    rule_set_id=rule_set.rule_set_id,
                    rule_set_version=rule_set.version,
                    profile_snapshot_id=state.qualification_profile_snapshot_id,
                    major_catalog=self._major_catalog,
                    major_mapping=self._major_mapping,
                    evaluated_at=created_at,
                    created_at=created_at,
                )
            )
            rankable.append(
                RankableMatch(
                    public_id=candidate.public_id,
                    opportunity_id=candidate.opportunity_id,
                    opportunity_version=candidate.opportunity_version,
                    match_snapshot_id=match.snapshot_id,
                    eligibility_status=match.eligibility_result.status,
                    opportunity_type=candidate.opportunity_type,
                    locations=candidate.locations,
                    public_status=candidate.public_status,
                    deadline=candidate.deadline,
                )
            )
            match_inputs.append(
                {
                    "opportunity_id": str(candidate.opportunity_id),
                    "opportunity_version": candidate.opportunity_version,
                    "match_input_sha256": match.input_sha256,
                    "eligibility_status": match.eligibility_result.status.value,
                }
            )
        items = rank_personal_matches(tuple(rankable), state)
        input_sha256 = _ranking_input_sha256(
            principal.user_id,
            state,
            tuple(match_inputs),
            tuple(omitted),
        )
        with self._session_factory() as session:
            existing = self._existing_by_hash(session, principal.user_id, input_sha256)
            if existing is not None:
                session.rollback()
                return existing
            snapshot_id = self._id_factory()
            snapshot = PersonalRankingSnapshotModel(
                ranking_snapshot_id=snapshot_id,
                user_id=principal.user_id,
                user_state_snapshot_id=state.user_state_snapshot_id,
                qualification_profile_snapshot_id=state.qualification_profile_snapshot_id,
                qualification_profile_version=state.qualification_profile_version,
                scenario_clock=state.scenario_clock,
                window_end=state.scenario_clock + timedelta(days=90),
                ranker_version=RANKER_VERSION,
                input_sha256=input_sha256,
                omitted_rule_set_count=len(omitted),
                created_at=created_at,
            )
            try:
                session.add(snapshot)
                session.flush()
                session.add_all(
                    [
                        PersonalRankingItemModel(
                            ranking_snapshot_id=snapshot_id,
                            ordinal=item.ordinal,
                            user_id=principal.user_id,
                            opportunity_id=item.opportunity_id,
                            opportunity_version=item.opportunity_version,
                            match_snapshot_id=item.match_snapshot_id,
                            eligibility_status=item.eligibility_status.value,
                            reason_codes=[reason.value for reason in item.reason_codes],
                            deadline=item.deadline,
                        )
                        for item in items
                    ]
                )
                session.commit()
                return self._contract_from_row(session, snapshot)
            except IntegrityError:
                session.rollback()
                existing = self._existing_by_hash(session, principal.user_id, input_sha256)
                if existing is not None:
                    return existing
                raise
            except Exception:
                session.rollback()
                raise

    def get_latest(
        self,
        principal: Principal,
    ) -> PersonalRankingSnapshotSchemaV05 | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(PersonalRankingSnapshotModel)
                .join(
                    UserStateSnapshotModel,
                    UserStateSnapshotModel.user_state_snapshot_id
                    == PersonalRankingSnapshotModel.user_state_snapshot_id,
                )
                .where(PersonalRankingSnapshotModel.user_id == principal.user_id)
                .order_by(
                    UserStateSnapshotModel.version.desc(),
                    PersonalRankingSnapshotModel.created_at.desc(),
                    PersonalRankingSnapshotModel.ranking_snapshot_id.desc(),
                )
                .limit(1)
            )
            return None if row is None else self._contract_from_row(session, row)

    def get_snapshot(
        self,
        principal: Principal,
        snapshot_id: UUID,
    ) -> PersonalRankingSnapshotSchemaV05 | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(PersonalRankingSnapshotModel).where(
                    PersonalRankingSnapshotModel.ranking_snapshot_id == snapshot_id,
                    PersonalRankingSnapshotModel.user_id == principal.user_id,
                )
            )
            return None if row is None else self._contract_from_row(session, row)

    def _load_public_candidates(
        self,
        state: UserStateSnapshotSchemaV05,
    ) -> tuple[_PublicCandidate, ...]:
        with self._session_factory() as session:
            rows = session.execute(
                select(Opportunity, OpportunityVersion)
                .join(
                    PublicCatalogEntry,
                    PublicCatalogEntry.opportunity_id == Opportunity.opportunity_id,
                )
                .join(
                    OpportunityVersion,
                    and_(
                        OpportunityVersion.opportunity_id == PublicCatalogEntry.opportunity_id,
                        OpportunityVersion.version == PublicCatalogEntry.opportunity_version,
                    ),
                )
                .where(
                    Opportunity.publication_status == "PUBLISHED",
                    Opportunity.current_version == PublicCatalogEntry.opportunity_version,
                )
                .order_by(Opportunity.public_id)
            ).all()
        window_end = state.scenario_clock + timedelta(days=90)
        candidates: list[_PublicCandidate] = []
        for opportunity, version in rows:
            snapshot = version.snapshot
            application_window = snapshot.get("application_window")
            if not isinstance(application_window, dict):
                raise PersonalMatchError("public opportunity has no application window")
            closes_on = application_window.get("closes_on")
            locations = snapshot.get("locations")
            if not isinstance(closes_on, str) or not isinstance(locations, list):
                raise PersonalMatchError("public opportunity has invalid matching fields")
            try:
                status = OpportunityStatus(str(snapshot["status"]))
                deadline = date.fromisoformat(closes_on)
                opportunity_type = OpportunityTypeV02(opportunity.type)
            except (KeyError, TypeError, ValueError) as error:
                raise PersonalMatchError(
                    "public opportunity has invalid matching fields"
                ) from error
            if (
                status not in {OpportunityStatus.OPEN, OpportunityStatus.CLOSING_SOON}
                or deadline < state.scenario_clock
                or deadline > window_end
            ):
                continue
            candidates.append(
                _PublicCandidate(
                    public_id=opportunity.public_id,
                    opportunity_id=opportunity.opportunity_id,
                    opportunity_version=version.version,
                    opportunity_type=opportunity_type,
                    locations=tuple(str(item) for item in locations),
                    public_status=status,
                    deadline=deadline,
                )
            )
        return tuple(candidates)

    def _rule_set_for(self, candidate: _PublicCandidate) -> RuleSetModel | None:
        with self._session_factory() as session:
            return session.scalar(
                select(RuleSetModel)
                .where(
                    RuleSetModel.opportunity_id == candidate.opportunity_id,
                    RuleSetModel.opportunity_version == candidate.opportunity_version,
                    RuleSetModel.review_status == "APPROVED",
                )
                .order_by(RuleSetModel.version.desc(), RuleSetModel.rule_set_id)
                .limit(1)
            )

    @staticmethod
    def _existing_by_hash(
        session: Session,
        user_id: UUID,
        input_sha256: str,
    ) -> PersonalRankingSnapshotSchemaV05 | None:
        row = session.scalar(
            select(PersonalRankingSnapshotModel).where(
                PersonalRankingSnapshotModel.user_id == user_id,
                PersonalRankingSnapshotModel.input_sha256 == input_sha256,
            )
        )
        return None if row is None else PersonalMatchService._contract_from_row(session, row)

    @staticmethod
    def _contract_from_row(
        session: Session,
        row: PersonalRankingSnapshotModel,
    ) -> PersonalRankingSnapshotSchemaV05:
        item_rows = session.scalars(
            select(PersonalRankingItemModel)
            .where(
                PersonalRankingItemModel.ranking_snapshot_id == row.ranking_snapshot_id,
                PersonalRankingItemModel.user_id == row.user_id,
            )
            .order_by(PersonalRankingItemModel.ordinal)
        ).all()
        return PersonalRankingSnapshotSchemaV05.model_validate(
            {
                "ranking_snapshot_id": row.ranking_snapshot_id,
                "user_state_snapshot_id": row.user_state_snapshot_id,
                "qualification_profile_snapshot_id": (row.qualification_profile_snapshot_id),
                "qualification_profile_version": row.qualification_profile_version,
                "scenario_clock": row.scenario_clock,
                "window_end": row.window_end,
                "ranker_version": row.ranker_version,
                "input_sha256": row.input_sha256,
                "items": [
                    {
                        "ordinal": item.ordinal,
                        "opportunity_id": item.opportunity_id,
                        "opportunity_version": item.opportunity_version,
                        "match_snapshot_id": item.match_snapshot_id,
                        "eligibility_status": item.eligibility_status,
                        "reason_codes": item.reason_codes,
                        "deadline": item.deadline,
                    }
                    for item in item_rows
                ],
                "omitted_rule_set_count": row.omitted_rule_set_count,
                "created_at": row.created_at,
            }
        )


def _ranking_input_sha256(
    user_id: UUID,
    state: UserStateSnapshotSchemaV05,
    matches: tuple[dict[str, object], ...],
    omitted: tuple[tuple[UUID, int], ...],
) -> str:
    payload = {
        "user_id": str(user_id),
        "user_state_snapshot_id": str(state.user_state_snapshot_id),
        "user_state_input_sha256": state.input_sha256,
        "qualification_profile_snapshot_id": str(state.qualification_profile_snapshot_id),
        "qualification_profile_version": state.qualification_profile_version,
        "scenario_clock": state.scenario_clock.isoformat(),
        "ranker_version": RANKER_VERSION,
        "matches": sorted(matches, key=lambda item: str(item["opportunity_id"])),
        "omitted_rule_sets": [
            {"opportunity_id": str(opportunity_id), "opportunity_version": version}
            for opportunity_id, version in sorted(omitted, key=lambda item: str(item[0]))
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = [
    "PersonalMatchError",
    "PersonalMatchService",
    "RANKER_VERSION",
    "RankableMatch",
    "rank_personal_matches",
]
