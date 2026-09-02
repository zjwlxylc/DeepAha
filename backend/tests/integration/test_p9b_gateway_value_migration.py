import re
from uuid import UUID, uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.p9b.models import ModelCall
from tests.integration.p9b_gateway_support import persist_model_call, seed_gateway_authority

pytestmark = pytest.mark.integration


def _temporary_database(database_url: str, prefix: str) -> tuple[str, Engine, URL, str]:
    database_name = f"{prefix}_{uuid4().hex}"
    assert re.fullmatch(r"[a-z0-9_]+_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance_engine = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    temporary_url = url.set(database=database_name)
    return (
        database_name,
        maintenance_engine,
        temporary_url,
        temporary_url.render_as_string(hide_password=False),
    )


def _drop_database(database_name: str, maintenance_engine: Engine) -> None:
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
    maintenance_engine.dispose()


def _replace_function_condition(
    engine: Engine,
    *,
    signature: str,
    current: str,
    replacement: str,
) -> None:
    with engine.begin() as connection:
        definition = connection.scalar(
            text("select pg_get_functiondef(to_regprocedure(:signature))"),
            {"signature": signature},
        )
        assert isinstance(definition, str)
        assert current in definition
        connection.exec_driver_sql(definition.replace(current, replacement).replace("%", "%%"))


def _add_current_bundle_compatibility_columns(engine: Engine) -> None:
    """Let current provenance helpers seed a historical P9-B schema."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE source_bundles "
            "ADD COLUMN request_key varchar(128), "
            "ADD COLUMN request_payload_sha256 varchar(64)"
        )
        connection.exec_driver_sql(
            "ALTER TABLE source_bundle_members "
            "ADD COLUMN evidence_ref_id uuid, "
            "ADD COLUMN parse_attempt_id uuid"
        )


def _begin_attempt(session: Session, call_id: UUID) -> UUID:
    attempt_id = uuid7()
    session.execute(
        text(
            "insert into p9b_model_call_attempts "
            "(model_call_id, attempt_number, attempt_id, authorization_decision, "
            "authorization_reason_code, authorization_checked_at, "
            "provider_invocation_allowed, created_at) values "
            "(:call_id, 1, :attempt_id, 'AUTHORITY_REJECTED', 'PENDING', "
            "clock_timestamp(), false, clock_timestamp())"
        ),
        {"call_id": call_id, "attempt_id": attempt_id},
    )
    return attempt_id


def _finish_historical_success(
    session: Session,
    *,
    attempt_id: UUID,
    provider_response_id: str | None,
    object_key: str | None = None,
    raw_response_sha256: str | None = None,
) -> None:
    internal = object_key is not None
    session.execute(
        text(
            "update p9b_model_call_attempts set outcome = 'SUCCEEDED', "
            "provider_http_status = 200, provider_response_id = :provider_response_id, "
            "raw_response_reference_kind = :kind, "
            "raw_response_storage_bucket = :bucket, raw_response_object_key = :object_key, "
            "raw_response_sha256 = :raw_hash, response_hash = :response_hash, "
            "parsed_result_hash = :parsed_hash, input_tokens = 1, output_tokens = 1, "
            "cache_read_tokens = 0, cache_write_tokens = 0, "
            "cost_status = 'COST_NOT_REPORTED', monetary_cost = null, latency_ms = 1, "
            "completed_at = clock_timestamp() where attempt_id = :attempt_id"
        ),
        {
            "provider_response_id": provider_response_id,
            "kind": "INTERNAL_OBJECT" if internal else "PROVIDER_RESPONSE_ID",
            "bucket": "model-audit" if internal else None,
            "object_key": object_key,
            "raw_hash": (
                raw_response_sha256
                if internal and raw_response_sha256 is not None
                else "7" * 64
                if internal
                else None
            ),
            "response_hash": "8" * 64,
            "parsed_hash": "9" * 64,
            "attempt_id": attempt_id,
        },
    )


def test_compliant_history_round_trips_through_value_contract_migration(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url,
        "deepaha_p9b_value_compliant",
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "20260825_0028")
        engine = create_engine(temporary_url)
        _add_current_bundle_compatibility_columns(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory.begin() as session:
            authority = seed_gateway_authority(session)
            persist_model_call(session, authority.intent)
            attempt_id = _begin_attempt(session, authority.intent.model_call_id)
            _finish_historical_success(
                session,
                attempt_id=attempt_id,
                provider_response_id="response_01JHISTORY",
            )

        command.upgrade(config, "20260825_0029")
        command.downgrade(config, "20260825_0028")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("select to_regprocedure('p9b_gateway_string_value_allowed(text,text)')")
                )
                is None
            )
            assert (
                connection.scalar(
                    text(
                        "select p9b_gateway_contains_credential_material("
                        "'xoxb-123456789012-abcdefghijklmnopqrstuv')"
                    )
                )
                is False
            )
        command.upgrade(config, "20260825_0029")
        with engine.connect() as connection:
            assert connection.scalar(text("select version_num from alembic_version")) == (
                "20260825_0029"
            )
            assert connection.scalar(text("select count(*) from p9b_model_calls")) == 1
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)


def test_head_repairs_preexisting_0032_public_official_training_policy(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url,
        "deepaha_p9b_public_policy_repair",
    )
    engine = None
    provider_condition = (
        "(NOT policy.training_use OR policy.allowed_classifications = "
        "ARRAY['PUBLIC_OFFICIAL_GENERAL']::text[])"
    )
    authority_condition = (
        "(NOT provider_policy.training_use OR "
        "provider_policy.allowed_classifications = "
        "ARRAY['PUBLIC_OFFICIAL_GENERAL']::text[])"
    )
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "20260826_0032")
        engine = create_engine(temporary_url)
        _replace_function_condition(
            engine,
            signature="p9b_guard_model_call_attempt()",
            current=provider_condition,
            replacement="NOT policy.training_use",
        )
        _replace_function_condition(
            engine,
            signature="p9b_egress_decision_authorized_at(uuid,timestamptz)",
            current=authority_condition,
            replacement="NOT provider_policy.training_use",
        )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            attempt_guard = connection.scalar(
                text("select pg_get_functiondef('p9b_guard_model_call_attempt()'::regprocedure)")
            )
            authority = connection.scalar(
                text(
                    "select pg_get_functiondef("
                    "'p9b_egress_decision_authorized_at(uuid,timestamptz)'::regprocedure)"
                )
            )
            assert provider_condition in attempt_guard
            assert authority_condition in authority
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)


@pytest.mark.parametrize(
    "unsafe_location",
    ["model_id", "provider_response_id", "object_key", "raw_response_sha256"],
)
def test_noncompliant_history_is_rejected_without_rewrite(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_location: str,
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url,
        f"deepaha_p9b_value_{unsafe_location}",
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "20260825_0028")
        engine = create_engine(temporary_url)
        _add_current_bundle_compatibility_columns(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory.begin() as session:
            authority = seed_gateway_authority(session)
            if unsafe_location == "model_id":
                values = authority.intent.model_dump(mode="python")
                values["model_id"] = "sk-proj-abcdefghijklmnopqrstuv"
                session.add(ModelCall(**values))
                session.flush()
            else:
                persist_model_call(session, authority.intent)
                attempt_id = _begin_attempt(session, authority.intent.model_call_id)
                _finish_historical_success(
                    session,
                    attempt_id=attempt_id,
                    provider_response_id=(
                        "xoxb-123456789012-abcdefghijklmnopqrstuv"
                        if unsafe_location == "provider_response_id"
                        else None
                    ),
                    object_key=(
                        "p9b/result.json?X-Amz-Signature=synthetic-signature"
                        if unsafe_location == "object_key"
                        else "p9b/result.json"
                        if unsafe_location == "raw_response_sha256"
                        else None
                    ),
                    raw_response_sha256=(
                        "A" * 64 if unsafe_location == "raw_response_sha256" else None
                    ),
                )

        with pytest.raises(DBAPIError, match="P9B_GATEWAY_STRING_PREFLIGHT_FAILED"):
            command.upgrade(config, "20260825_0029")
        with engine.connect() as connection:
            assert connection.scalar(text("select version_num from alembic_version")) == (
                "20260825_0028"
            )
            if unsafe_location == "model_id":
                retained = connection.scalar(text("select model_id from p9b_model_calls"))
            elif unsafe_location == "provider_response_id":
                retained = connection.scalar(
                    text("select provider_response_id from p9b_model_call_attempts")
                )
            elif unsafe_location == "object_key":
                retained = connection.scalar(
                    text("select raw_response_object_key from p9b_model_call_attempts")
                )
            else:
                retained = connection.scalar(
                    text("select raw_response_sha256 from p9b_model_call_attempts")
                )
            assert retained is not None
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)
