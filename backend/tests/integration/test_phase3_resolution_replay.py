import re
from pathlib import Path
from uuid import uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from deepaha.opportunities.models import (
    Opportunity,
    OpportunityEvent,
    OpportunityResolutionCandidate,
    OpportunityVersion,
)
from deepaha.opportunities.service import OpportunityResolutionService

from .test_opportunity_resolution_service import (
    CLOCK_TIME,
    PUBLIC_ID,
    commands_by_id,
    happy_path_commands,
    seed_conflict_target,
    seed_fixture_documents,
)

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).parents[2]


def run_synthetic_replay(database_url: URL) -> dict[str, object]:
    engine = create_engine(database_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        seed_fixture_documents(factory)
        service = OpportunityResolutionService(
            session_factory=factory,
            clock=lambda: CLOCK_TIME,
            id_factory=uuid7,
        )
        for fixture_command in happy_path_commands():
            service.resolve(fixture_command)
        seed_conflict_target(factory)
        commands = commands_by_id()
        service.resolve(commands["lower_priority_conflict"])
        service.resolve(commands["possible_false_merge"])

        with factory() as session:
            opportunity = session.scalar(
                select(Opportunity).where(Opportunity.public_id == PUBLIC_ID)
            )
            assert opportunity is not None
            versions = session.scalars(
                select(OpportunityVersion)
                .where(OpportunityVersion.opportunity_id == opportunity.opportunity_id)
                .order_by(OpportunityVersion.version)
            ).all()
            events = session.scalars(
                select(OpportunityEvent)
                .where(OpportunityEvent.opportunity_id == opportunity.opportunity_id)
                .order_by(OpportunityEvent.to_version)
            ).all()
            candidates = session.scalars(
                select(OpportunityResolutionCandidate).order_by(
                    OpportunityResolutionCandidate.document_id
                )
            ).all()
            return {
                "public_id": opportunity.public_id,
                "versions": [item.version for item in versions],
                "hashes": [item.content_sha256 for item in versions],
                "event_types": [item.event_type for item in events],
                "changed_fields": [item.changed_fields for item in events],
                "candidate_reasons": [item.reason_codes for item in candidates],
                "projection": {
                    "canonical_title": opportunity.canonical_title,
                    "type": opportunity.type,
                    "issuer_name": opportunity.issuer_name,
                    "jurisdiction": opportunity.jurisdiction,
                    "status": opportunity.status,
                    "current_version": opportunity.current_version,
                },
            }
    finally:
        engine.dispose()


def test_fixed_fixture_replay_matches_in_two_fresh_databases(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url = make_url(database_url)
    maintenance_url = base_url.set(database="postgres")
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    outputs: list[dict[str, object]] = []
    try:
        for _ in range(2):
            database_name = f"deepaha_replay_{uuid4().hex}"
            assert re.fullmatch(r"deepaha_replay_[0-9a-f]{32}", database_name)
            replay_url = base_url.set(database=database_name)
            with maintenance_engine.connect() as connection:
                connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            try:
                monkeypatch.setenv(
                    "DEEPAHA_DATABASE_URL",
                    replay_url.render_as_string(hide_password=False),
                )
                command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
                outputs.append(run_synthetic_replay(replay_url))
            finally:
                with maintenance_engine.connect() as connection:
                    connection.exec_driver_sql(
                        f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'
                    )
    finally:
        maintenance_engine.dispose()

    assert outputs[0] == outputs[1]
    assert outputs[0]["public_id"] == PUBLIC_ID
    assert outputs[0]["versions"] == [1, 2, 3, 4, 5, 6]
    assert outputs[0]["event_types"] == [
        "CREATED",
        "ATTACHMENT_REPLACED",
        "ATTACHMENT_REPLACED",
        "CORRECTED",
        "DEADLINE_CHANGED",
        "CANCELLED",
    ]
    assert outputs[0]["candidate_reasons"] == [
        ["STRONG_KEY_CONFLICT"],
        ["POSSIBLE_DUPLICATE"],
    ]
