import re
from dataclasses import replace
from uuid import UUID, uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import sessionmaker

from deepaha.documents.models import Document, ParseAttempt
from tests.integration.test_p9b_b0_persistence import NOW, Graph, member_spec, seed_graph

pytestmark = pytest.mark.integration
MAIN_HEAD = "20260826_0033"


def temporary_database(database_url: str, prefix: str) -> tuple[str, Engine, URL, str]:
    database_name = f"{prefix}_{uuid4().hex}"
    assert re.fullmatch(r"[a-z0-9_]+_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    temporary_url = url.set(database=database_name)
    return (
        database_name,
        maintenance_engine,
        temporary_url,
        temporary_url.render_as_string(hide_password=False),
    )


def drop_temporary_database(database_name: str, maintenance_engine: Engine) -> None:
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
    maintenance_engine.dispose()


def seed_legacy_opportunity_bundle(engine: Engine) -> tuple[UUID, UUID]:
    opportunity_id = UUID("019c0000-0000-7000-8000-000000001101")
    bundle_id = UUID("019c0000-0000-7000-8000-000000001102")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "insert into opportunities (opportunity_id, public_id, type, canonical_title, "
            "issuer_name, jurisdiction, current_version, status, publication_status, "
            f"created_at, updated_at) values ('{opportunity_id}', 'opp_{opportunity_id.hex}', "
            "'PUBLIC_INSTITUTION_JOB', 'Legacy opportunity', 'Synthetic authority', null, "
            "null, 'DRAFT', 'INTERNAL', now(), now())"
        )
        connection.exec_driver_sql(
            "insert into source_bundles (source_bundle_id, opportunity_id, created_at, "
            f"retired_at) values ('{bundle_id}', '{opportunity_id}', now(), null)"
        )
    return opportunity_id, bundle_id


def seed_full_legacy_bundle(engine: Engine) -> tuple[Graph, UUID, UUID, UUID]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        graph = seed_graph(session, suffix="p10b1-migration")
        bundle_id = uuid7()
        revision_id = uuid7()
        member_id = uuid7()
        session.execute(
            text(
                "insert into source_bundles "
                "(source_bundle_id, opportunity_id, created_at, retired_at) "
                "values (:bundle_id, :opportunity_id, :now, null)"
            ),
            {"bundle_id": bundle_id, "opportunity_id": graph.opportunity_id, "now": NOW},
        )
        session.execute(
            text(
                "insert into source_bundle_revisions "
                "(source_bundle_revision_id, source_bundle_id, opportunity_id, "
                "opportunity_version, revision_number, canonical_bundle_hash, "
                "relation_graph_version, precedence_graph_version, effective_as_of, "
                "status, created_at, frozen_at) values "
                "(:revision_id, :bundle_id, :opportunity_id, 1, 1, :zero_hash, "
                "'p9b-member-relation-v0.8.0', 'p9b-precedence-v0.8.0', :now, "
                "'DRAFT', :now, null)"
            ),
            {
                "revision_id": revision_id,
                "bundle_id": bundle_id,
                "opportunity_id": graph.opportunity_id,
                "zero_hash": "0" * 64,
                "now": NOW,
            },
        )
        session.execute(
            text(
                "insert into source_bundle_members "
                "(source_bundle_member_id, source_bundle_revision_id, source_id, endpoint_id, "
                "capture_observation_id, acquisition_evaluation_id, "
                "acquisition_validation_status, acquisition_run_id, recipe_id, recipe_version, "
                "policy_version, fetch_strategy, fetcher_name, fetcher_version, validator_name, "
                "validator_version, raw_artifact_id, raw_artifact_sha256, raw_artifact_size, "
                "storage_bucket, object_key, document_id, document_parse_key, parser_name, "
                "parser_version, parse_contract_version, member_role, precedence, effective_from, "
                "effective_to, member_provenance_hash, created_at) "
                "select :member_id, :revision_id, observation.source_id, observation.endpoint_id, "
                "observation.observation_id, evaluation.acquisition_evaluation_id, "
                "evaluation.validation_status, run.acquisition_run_id, run.recipe_id, "
                "run.recipe_version, observation.policy_version, evaluation.strategy_used, "
                "observation.collector_name, observation.collector_version, "
                "evaluation.validator_name, evaluation.validator_version, artifact.artifact_id, "
                "artifact.content_sha256, artifact.byte_size, artifact.storage_bucket, "
                "artifact.object_key, document.document_id, document.document_parse_key, "
                "document.parser_name, document.parser_version, document.parse_contract_version, "
                "'PRIMARY_NOTICE', 1000, :now, null, :zero_hash, :now "
                "from documents document "
                "join raw_artifacts artifact on artifact.artifact_id = document.artifact_id "
                "join capture_observations observation "
                "on observation.observation_id = :observation_id "
                "join acquisition_evaluations evaluation "
                "on evaluation.acquisition_evaluation_id = :evaluation_id "
                "join acquisition_runs run on run.acquisition_run_id = :run_id "
                "where document.document_id = :document_id"
            ),
            {
                "member_id": member_id,
                "revision_id": revision_id,
                "observation_id": graph.observation_id,
                "evaluation_id": graph.evaluation_id,
                "run_id": graph.run_id,
                "document_id": graph.document_id,
                "zero_hash": "0" * 64,
                "now": NOW,
            },
        )
        session.execute(
            text(
                "alter table source_bundle_members disable trigger "
                "source_bundle_members_reject_mutation"
            )
        )
        session.execute(
            text(
                "update source_bundle_members set member_provenance_hash = "
                "p9b_expected_member_hash(:member_id) where source_bundle_member_id = :member_id"
            ),
            {"member_id": member_id},
        )
        session.execute(
            text(
                "alter table source_bundle_members enable trigger "
                "source_bundle_members_reject_mutation"
            )
        )
        session.execute(
            text(
                "update source_bundle_revisions set canonical_bundle_hash = "
                "p9b_expected_bundle_hash(:revision_id), status = 'FROZEN', frozen_at = :now "
                "where source_bundle_revision_id = :revision_id"
            ),
            {"revision_id": revision_id, "now": NOW},
        )
    return graph, bundle_id, revision_id, member_id


def test_upgrade_from_main_head_preserves_legacy_bundle_and_round_trips(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name, maintenance_engine, temporary_url, rendered_url = temporary_database(
        database_url, "deepaha_p10b1_legacy"
    )
    temporary_engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered_url)
        config = Config("alembic.ini")
        command.upgrade(config, MAIN_HEAD)
        temporary_engine = create_engine(temporary_url)
        opportunity_id, bundle_id = seed_legacy_opportunity_bundle(temporary_engine)

        command.upgrade(config, "head")
        with temporary_engine.connect() as connection:
            upgraded_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("source_bundles")
            }
            assert {"request_key", "request_payload_sha256"} <= upgraded_columns.keys()
            assert upgraded_columns["opportunity_id"]["nullable"] is True
            row = connection.exec_driver_sql(
                "select opportunity_id, request_key, request_payload_sha256 "
                f"from source_bundles where source_bundle_id = '{bundle_id}'"
            ).one()
            assert row == (opportunity_id, None, None)

        command.downgrade(config, MAIN_HEAD)
        with temporary_engine.connect() as connection:
            downgraded_columns = {
                column["name"] for column in inspect(connection).get_columns("source_bundles")
            }
            assert {"request_key", "request_payload_sha256"}.isdisjoint(downgraded_columns)
            assert (
                connection.exec_driver_sql(
                    "select opportunity_id from source_bundles where source_bundle_id = "
                    f"'{bundle_id}'"
                ).scalar_one()
                == opportunity_id
            )

        command.upgrade(config, "head")
        with temporary_engine.connect() as connection:
            assert (
                connection.exec_driver_sql("select version_num from alembic_version").scalar_one()
                == ScriptDirectory.from_config(config).get_current_head()
            )
            assert (
                connection.exec_driver_sql(
                    "select opportunity_id from source_bundles where source_bundle_id = "
                    f"'{bundle_id}'"
                ).scalar_one()
                == opportunity_id
            )
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        drop_temporary_database(database_name, maintenance_engine)


def test_full_frozen_legacy_bundle_supports_new_revision_and_round_trip(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepaha.p9b.provenance import BundleService

    database_name, maintenance_engine, temporary_url, rendered_url = temporary_database(
        database_url, "deepaha_p10b1_full_legacy"
    )
    temporary_engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered_url)
        config = Config("alembic.ini")
        command.upgrade(config, MAIN_HEAD)
        temporary_engine = create_engine(temporary_url)
        graph, bundle_id, legacy_revision_id, legacy_member_id = seed_full_legacy_bundle(
            temporary_engine
        )

        # Current ORM runs against current head; the legacy fixture and the
        # downgrade to MAIN_HEAD still exercise 0034's original hash contract.
        command.upgrade(config, "head")
        factory = sessionmaker(bind=temporary_engine, expire_on_commit=False)
        with factory.begin() as session:
            revision = BundleService(session).create_revision(
                opportunity_id=graph.opportunity_id,
                opportunity_version=graph.opportunity_version,
                effective_as_of=NOW,
                members=[member_spec(graph)],
                source_bundle_id=bundle_id,
            )
            frozen = BundleService(session).freeze_revision(
                revision.source_bundle_revision_id,
                frozen_at=NOW,
            )
            new_revision_id = frozen.source_bundle_revision_id

        with temporary_engine.connect() as connection:
            legacy_binding = connection.execute(
                text(
                    "select evidence_ref_id, parse_attempt_id from source_bundle_members "
                    "where source_bundle_member_id = :member_id"
                ),
                {"member_id": legacy_member_id},
            ).one()
            assert legacy_binding == (None, None)
            assert (
                connection.scalar(
                    text(
                        "select count(*) from source_bundle_revisions "
                        "where source_bundle_id = :bundle_id and status = 'FROZEN'"
                    ),
                    {"bundle_id": bundle_id},
                )
                == 2
            )

        command.downgrade(config, MAIN_HEAD)
        with temporary_engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "select count(*) from source_bundle_revisions "
                        "where source_bundle_id = :bundle_id and status = 'FROZEN'"
                    ),
                    {"bundle_id": bundle_id},
                )
                == 2
            )
            assert {
                legacy_revision_id,
                new_revision_id,
            } == set(
                connection.scalars(
                    text(
                        "select source_bundle_revision_id from source_bundle_revisions "
                        "where source_bundle_id = :bundle_id"
                    ),
                    {"bundle_id": bundle_id},
                )
            )
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        drop_temporary_database(database_name, maintenance_engine)


def test_downgrade_refuses_opportunity_member_with_exact_evidence_binding(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepaha.p9b.provenance import BundleService

    database_name, maintenance_engine, temporary_url, rendered_url = temporary_database(
        database_url, "deepaha_p10b1_bound_opportunity"
    )
    temporary_engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered_url)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        temporary_engine = create_engine(temporary_url)
        factory = sessionmaker(bind=temporary_engine, expire_on_commit=False)
        with factory.begin() as session:
            graph = seed_graph(session, suffix="p10b1-bound-opportunity")
            document = session.get(Document, graph.document_id)
            assert document is not None
            parse_attempt = ParseAttempt(
                parse_attempt_id=uuid7(),
                artifact_id=document.artifact_id,
                parser_name=document.parser_name,
                parser_version=document.parser_version,
                parse_contract_version=document.parse_contract_version,
                document_parse_key=document.document_parse_key,
                started_at=NOW,
                completed_at=NOW,
                outcome="SUCCEEDED",
                document_id=document.document_id,
                error_code=None,
                input_media_type="text/html",
            )
            session.add(parse_attempt)
            session.flush()
            service = BundleService(session)
            revision = service.create_revision(
                opportunity_id=graph.opportunity_id,
                opportunity_version=graph.opportunity_version,
                effective_as_of=NOW,
                members=[
                    replace(
                        member_spec(graph),
                        evidence_ref_id=graph.evidence_ref_id,
                        parse_attempt_id=parse_attempt.parse_attempt_id,
                    )
                ],
            )
            frozen = service.freeze_revision(revision.source_bundle_revision_id, frozen_at=NOW)
            revision_id = frozen.source_bundle_revision_id
            before_hash = frozen.canonical_bundle_hash

        with pytest.raises(RuntimeError, match="cannot downgrade P10-B1"):
            command.downgrade(config, MAIN_HEAD)

        with temporary_engine.connect() as connection:
            row = connection.execute(
                text(
                    "select canonical_bundle_hash, status from source_bundle_revisions "
                    "where source_bundle_revision_id = :revision_id"
                ),
                {"revision_id": revision_id},
            ).one()
            assert row == (before_hash, "FROZEN")
            assert (
                connection.scalar(text("select version_num from alembic_version"))
                == ScriptDirectory.from_config(config).get_current_head()
            )
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        drop_temporary_database(database_name, maintenance_engine)


def test_downgrade_refuses_request_bundle_without_deleting_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name, maintenance_engine, temporary_url, rendered_url = temporary_database(
        database_url, "deepaha_p10b1_refusal"
    )
    temporary_engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered_url)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        temporary_engine = create_engine(temporary_url)
        bundle_id = UUID("019c0000-0000-7000-8000-000000001202")
        with temporary_engine.begin() as connection:
            connection.exec_driver_sql(
                "insert into source_bundles (source_bundle_id, opportunity_id, request_key, "
                "request_payload_sha256, created_at, retired_at) values "
                f"('{bundle_id}', null, 'synthetic:request:1', '{'a' * 64}', now(), null)"
            )

        with pytest.raises(RuntimeError, match="cannot downgrade P10-B1"):
            command.downgrade(config, MAIN_HEAD)

        with temporary_engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    f"select request_key from source_bundles where source_bundle_id = '{bundle_id}'"
                ).scalar_one()
                == "synthetic:request:1"
            )
            assert (
                connection.exec_driver_sql("select version_num from alembic_version").scalar_one()
                == ScriptDirectory.from_config(config).get_current_head()
            )
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        drop_temporary_database(database_name, maintenance_engine)
