from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.personal.auth import token_digest
from deepaha.personal.models import PersonalAuthSessionModel, PersonalUserModel
from deepaha.personal.schemas import ProfileWrite
from deepaha.rules.models import RuleEvidenceModel, RuleModel, RuleSetModel
from tests.public_catalog.support import persist_phase5_fixture, stable_uuid7

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "personal"
FIXTURE_PATH = FIXTURE_ROOT / "phase6-users.json"
MANIFEST_PATH = FIXTURE_ROOT / "phase6-users.manifest.json"
FIXTURE_NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
FIXTURE_EXPIRES_AT = datetime(2099, 1, 1, tzinfo=UTC)
# Non-secret deterministic credentials accepted only by development/test fixture auth.
_SYNTHETIC_SESSION_TOKEN_A = "K7vJg8mQ2xN4pR6tV9yB3cD5fH1sW0zL"
_SYNTHETIC_SESSION_TOKEN_B = "T5nC9qA1uE7kM3rX8bF2hJ6pV4wY0sGd"


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FixtureUser(FixtureModel):
    key: str
    user_id: UUID
    user_state_id: UUID
    profile: ProfileWrite


class Phase6Fixture(FixtureModel):
    schema_version: Literal["phase6-personal-fixture-v1"]
    synthetic: Literal[True]
    contains_personal_data: Literal[False]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    license: Literal["CC0-1.0 synthetic fixture"]
    scenario_clock: Literal["2026-08-22"]
    users: tuple[FixtureUser, FixtureUser]


class FixtureManifest(FixtureModel):
    fixture: Literal["phase6-users.json"]
    sha256: str
    license: Literal["CC0-1.0 synthetic fixture"]
    synthetic: Literal[True]
    contains_personal_data: Literal[False]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    user_count: Literal[2]
    purpose: str


@dataclass(frozen=True, slots=True)
class Phase6FixtureIdentity:
    user_a_id: UUID
    user_b_id: UUID
    token_a: str
    token_b: str
    profile_a: ProfileWrite
    profile_b: ProfileWrite
    public_ids: tuple[str, ...]


def load_phase6_fixture() -> Phase6Fixture:
    fixture_bytes = FIXTURE_PATH.read_bytes()
    manifest = FixtureManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    if hashlib.sha256(fixture_bytes).hexdigest() != manifest.sha256:
        raise ValueError("Phase 6 fixture hash does not match its manifest")
    fixture = Phase6Fixture.model_validate_json(fixture_bytes)
    if len(fixture.users) != manifest.user_count:
        raise ValueError("Phase 6 fixture user count does not match its manifest")
    if len({user.user_id for user in fixture.users}) != len(fixture.users):
        raise ValueError("Phase 6 fixture user IDs must be unique")
    return fixture


def _persist_rule_sets(session: Session) -> None:
    opportunities = session.scalars(
        select(Opportunity)
        .where(Opportunity.status.in_(("OPEN", "CLOSING_SOON")))
        .order_by(Opportunity.public_id)
    ).all()
    for opportunity in opportunities:
        if opportunity.current_version is None:
            raise ValueError("Phase 6 fixture opportunity requires a current version")
        version = session.get(
            OpportunityVersion,
            (opportunity.opportunity_id, opportunity.current_version),
        )
        if version is None:
            raise ValueError("Phase 6 fixture opportunity version is missing")
        rule_set_id = stable_uuid7(f"phase6:{opportunity.public_id}:rule-set")
        rule_id = stable_uuid7(f"phase6:{opportunity.public_id}:education-rule")
        session.add(
            RuleSetModel(
                rule_set_id=rule_set_id,
                version=1,
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=version.version,
                root_rule_ids=[str(rule_id)],
                review_status="APPROVED",
                rule_schema_version="0.4.0",
                created_at=FIXTURE_NOW,
            )
        )
        session.flush()
        session.add(
            RuleModel(
                rule_set_id=rule_set_id,
                rule_set_version=1,
                rule_id=rule_id,
                code="phase6-fixture-education-bachelor",
                operator="EQ",
                field="education_level",
                value_type="STRING",
                value="BACHELOR",
                operand_rule_ids=[],
                required=True,
                reason_template="合成夹具：学历为本科。",
            )
        )
        session.flush()
        session.add(
            RuleEvidenceModel(
                rule_set_id=rule_set_id,
                rule_set_version=1,
                rule_id=rule_id,
                evidence_ref_id=version.source_evidence_ref_id,
                document_id=version.source_document_id,
                authority="ORIGINAL_OFFICIAL_NOTICE",
                precedence=400,
                relation="SUPPORTS",
                effective_at=FIXTURE_NOW,
                assertion_sha256=version.content_sha256,
            )
        )
        session.flush()


def persist_phase6_fixture(session: Session) -> Phase6FixtureIdentity:
    fixture = load_phase6_fixture()
    public_ids = persist_phase5_fixture(session)
    _persist_rule_sets(session)
    for user, token in zip(
        fixture.users,
        (_SYNTHETIC_SESSION_TOKEN_A, _SYNTHETIC_SESSION_TOKEN_B),
        strict=True,
    ):
        session.add(
            PersonalUserModel(
                user_id=user.user_id,
                user_state_id=user.user_state_id,
                active=True,
                created_at=FIXTURE_NOW,
            )
        )
        session.flush()
        session.add(
            PersonalAuthSessionModel(
                token_sha256=token_digest(token),
                user_id=user.user_id,
                expires_at=FIXTURE_EXPIRES_AT,
                revoked_at=None,
                created_at=FIXTURE_NOW,
            )
        )
    session.flush()
    user_a, user_b = fixture.users
    return Phase6FixtureIdentity(
        user_a_id=user_a.user_id,
        user_b_id=user_b.user_id,
        token_a=_SYNTHETIC_SESSION_TOKEN_A,
        token_b=_SYNTHETIC_SESSION_TOKEN_B,
        profile_a=user_a.profile,
        profile_b=user_b.profile,
        public_ids=public_ids,
    )


__all__ = [
    "Phase6Fixture",
    "Phase6FixtureIdentity",
    "load_phase6_fixture",
    "persist_phase6_fixture",
]
