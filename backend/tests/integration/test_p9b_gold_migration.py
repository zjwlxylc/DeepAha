import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.p9b.gold import GoldRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)
JUDGMENT_A = json.dumps(
    [
        {
            "field_name": "application_deadline",
            "gold_state": "KNOWN_SUPPORTED",
            "normalized_value": "2026-09-01",
            "evidence_block_ids": [str(uuid7())],
            "high_impact": True,
            "precedence_sensitive": False,
        }
    ]
)
JUDGMENT_B = JUDGMENT_A.replace("2026-09-01", "2026-09-02")


def _temporary_database(database_url: str, prefix: str) -> tuple[str, Engine, URL, str]:
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


def _drop_database(database_name: str, maintenance_engine: Engine) -> None:
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
    maintenance_engine.dispose()


def _seed_frozen_calibration_manifest(connection: Connection) -> tuple[UUID, str]:
    manifest_id = uuid7()
    manifest_hash = sha256(str(manifest_id).encode()).hexdigest()
    connection.execute(
        text(
            "insert into dataset_manifests (dataset_manifest_id, split_manifest_version, "
            "partition, expected_entry_count, actual_entry_count, atomic_group_count, "
            "evaluation_cutoff, answer_access_class, status, frozen_by, created_at, frozen_at, "
            "invalidated_at, invalidation_reason, successor_manifest_hash, manifest_hash) "
            "values (:id, 'test-split-v1', 'CALIBRATION', 30, 0, 0, :now, "
            "'ASSISTED_CALIBRATION', 'DRAFT', 'human:curator-d', :now, null, null, null, null, "
            ":hash)"
        ),
        {"id": manifest_id, "now": NOW, "hash": manifest_hash},
    )
    connection.execute(text("alter table dataset_manifest_entries disable trigger all"))
    rows = []
    for index in range(30):
        rows.append(
            {
                "manifest_id": manifest_id,
                "entry_id": f"calibration-{index:03d}",
                "opportunity_id": uuid7(),
                "unit_id": uuid7(),
                "unit_version_id": uuid7(),
                "bundle_id": uuid7(),
                "revision_id": uuid7(),
                "hash": f"{index + 1:064x}",
                "atomic_group": f"atomic-{index:03d}",
                "near": json.dumps([f"near-{index:03d}"]),
                "lineage": "[]",
                "now": NOW,
            }
        )
    connection.execute(
        text(
            "insert into dataset_manifest_entries (dataset_manifest_id, entry_id, partition, "
            "opportunity_id, opportunity_version, opportunity_unit_id, "
            "opportunity_unit_version_id, source_bundle_id, source_bundle_revision_id, "
            "canonical_bundle_hash, atomic_group_id, near_duplicate_cluster_ids, "
            "unit_lineage_ids, evaluation_as_of, answer_access_class, created_at) values "
            "(:manifest_id, :entry_id, 'CALIBRATION', :opportunity_id, 1, :unit_id, "
            ":unit_version_id, :bundle_id, :revision_id, :hash, :atomic_group, "
            "cast(:near as jsonb), "
            "cast(:lineage as jsonb), :now, 'ASSISTED_CALIBRATION', :now)"
        ),
        rows,
    )
    connection.execute(text("alter table dataset_manifest_entries enable trigger all"))
    connection.execute(
        text(
            "update dataset_manifests set actual_entry_count = 30, atomic_group_count = 30, "
            "status = 'FROZEN', frozen_at = :now where dataset_manifest_id = :id"
        ),
        {"id": manifest_id, "now": NOW},
    )
    return manifest_id, "calibration-000"


def _insert_task(
    connection: Connection,
    manifest_id: UUID,
    entry_id: str,
    *,
    attestation_references: dict[str, str] | None = None,
) -> UUID:
    task_id = uuid7()
    connection.execute(
        text(
            "insert into gold_annotation_tasks (gold_annotation_task_id, dataset_manifest_id, "
            "entry_id, partition, answer_access_class, annotator_identity, verifier_identity, "
            "adjudicator_identity, curator_identity, role_attestation_references, "
            "blind_started_at, blind_ended_at, "
            "split_seed_reference, status, created_at) values (:task, :manifest, :entry, "
            "'CALIBRATION', 'ASSISTED_CALIBRATION', 'human:annotator-a', 'human:verifier-b', "
            "'human:adjudicator-c', 'human:curator-d', cast(:attestations as jsonb), :now, null, "
            "'local-secret-reference:test-split', 'BLIND_REVIEW', :now)"
        ),
        {
            "task": task_id,
            "manifest": manifest_id,
            "entry": entry_id,
            "attestations": json.dumps(
                attestation_references
                or {
                    "ANNOTATOR": "synthetic-fixture:annotator-a",
                    "VERIFIER": "synthetic-fixture:verifier-b",
                    "ADJUDICATOR": "synthetic-fixture:adjudicator-c",
                    "CURATOR": "synthetic-fixture:curator-d",
                }
            ),
            "now": NOW,
        },
    )
    return task_id


def _insert_submission(
    connection: Connection,
    *,
    task_id: UUID,
    submission_id: UUID,
    role: str,
    actor: str,
    judgments: str,
) -> None:
    connection.execute(
        text(
            "insert into gold_annotation_submissions (gold_annotation_submission_id, "
            "gold_annotation_task_id, review_role, actor_identity, assisted_calibration, "
            "judgments, submitted_at) values (:submission, :task, :role, :actor, false, "
            "cast(:judgments as jsonb), :now)"
        ),
        {
            "submission": submission_id,
            "task": task_id,
            "role": role,
            "actor": actor,
            "judgments": judgments,
            "now": NOW,
        },
    )


def test_gold_migration_empty_round_trip(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url, "deepaha_p9b_gold_empty"
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(temporary_url)
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            assert "gold_annotation_tasks" in tables
            assert "gold_truth_versions" in tables
        command.downgrade(config, "20260824_0013")
        with engine.connect() as connection:
            assert "gold_annotation_tasks" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)


def test_gold_migration_refuses_to_discard_governed_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url, "deepaha_p9b_gold_history"
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(temporary_url)
        with engine.begin() as connection:
            manifest_id, entry_id = _seed_frozen_calibration_manifest(connection)
            _insert_task(connection, manifest_id, entry_id)

        with pytest.raises(RuntimeError, match="cannot downgrade P9-B Gold history"):
            command.downgrade(config, "20260824_0013")
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)


def test_postgresql_enforces_gold_role_separation_and_conflict_adjudication(
    connection: Connection,
) -> None:
    transaction = connection.begin()
    try:
        manifest_id, entry_id = _seed_frozen_calibration_manifest(connection)
        attestation_ids = {
            role: uuid7() for role in ("ANNOTATOR", "VERIFIER", "ADJUDICATOR", "CURATOR")
        }
        task_id = _insert_task(
            connection,
            manifest_id,
            entry_id,
            attestation_references={
                role: f"gold-role-attestation:{attestation_id}"
                for role, attestation_id in attestation_ids.items()
            },
        )
        for role, subject in {
            "ANNOTATOR": "human:annotator-a",
            "VERIFIER": "human:verifier-b",
            "ADJUDICATOR": "human:adjudicator-c",
            "CURATOR": "human:curator-d",
        }.items():
            connection.execute(
                text(
                    "insert into gold_role_attestations (gold_role_attestation_id, "
                    "review_role, subject_identity, attestation_authority_identity, "
                    "verification_method, external_evidence_reference, "
                    "external_evidence_sha256, verified_at, expires_at, created_at) values "
                    "(:id, :role, :subject, 'human:untrusted-authority', "
                    "'SIGNED_ACCOUNT_ASSERTION', 'unverified:arbitrary-string', :hash, "
                    ":now, null, :now)"
                ),
                {
                    "id": attestation_ids[role],
                    "role": role,
                    "subject": subject,
                    "hash": sha256(f"{role}:arbitrary".encode()).hexdigest(),
                    "now": NOW,
                },
            )
        annotation_id = uuid7()
        verifier_id = uuid7()

        nested = connection.begin_nested()
        with pytest.raises(DBAPIError, match="GOLD_SUBMISSION_ROLE_OR_ASSISTANCE_MISMATCH"):
            _insert_submission(
                connection,
                task_id=task_id,
                submission_id=uuid7(),
                role="ANNOTATOR",
                actor="human:verifier-b",
                judgments=JUDGMENT_A,
            )
        nested.rollback()

        _insert_submission(
            connection,
            task_id=task_id,
            submission_id=annotation_id,
            role="ANNOTATOR",
            actor="human:annotator-a",
            judgments=JUDGMENT_A,
        )
        _insert_submission(
            connection,
            task_id=task_id,
            submission_id=verifier_id,
            role="VERIFIER",
            actor="human:verifier-b",
            judgments=JUDGMENT_B,
        )

        truth_sql = text(
            "insert into gold_truth_versions (gold_truth_version_id, gold_annotation_task_id, "
            "version, supersedes_truth_version_id, revision_reason_code, annotation_submission_id, "
            "verification_submission_id, adjudication_decision_id, curator_identity, judgments, "
            "truth_hash, frozen_at) values (:truth, :task, 1, null, 'INITIAL_FREEZE', :annotation, "
            ":verification, :adjudication, 'human:curator-d', cast(:judgments as jsonb), "
            ":hash, :now)"
        )
        nested = connection.begin_nested()
        with pytest.raises(DBAPIError, match="CONFLICTING_GOLD_REQUIRES_BOUND_ADJUDICATION"):
            connection.execute(
                truth_sql,
                {
                    "truth": uuid7(),
                    "task": task_id,
                    "annotation": annotation_id,
                    "verification": verifier_id,
                    "adjudication": None,
                    "judgments": JUDGMENT_A,
                    "hash": "b" * 64,
                    "now": NOW,
                },
            )
        nested.rollback()

        adjudication_id = uuid7()
        connection.execute(
            text(
                "insert into gold_adjudication_decisions (gold_adjudication_decision_id, "
                "gold_annotation_task_id, annotation_submission_id, verification_submission_id, "
                "adjudicator_identity, judgments, reason_code, decided_at) values "
                "(:decision, :task, :annotation, :verification, 'human:adjudicator-c', "
                "cast(:judgments as jsonb), 'OFFICIAL_PRECEDENCE_CONFIRMED', :now)"
            ),
            {
                "decision": adjudication_id,
                "task": task_id,
                "annotation": annotation_id,
                "verification": verifier_id,
                "judgments": JUDGMENT_A,
                "now": NOW,
            },
        )
        connection.execute(
            text(
                "insert into gold_answer_access_events (gold_answer_access_event_id, "
                "gold_annotation_task_id, requester_identity, requester_role, access_kind, "
                "decision, reason_code, occurred_at) values (:event, :task, "
                "'human:curator-d', 'CURATOR', 'GOLD_ANSWER', 'GRANTED', "
                "'BLIND_REVIEW_COMPLETED_AFTER_TWO_SUBMISSIONS', :now)"
            ),
            {"event": uuid7(), "task": task_id, "now": NOW},
        )
        truth_id = uuid7()
        connection.execute(
            truth_sql,
            {
                "truth": truth_id,
                "task": task_id,
                "annotation": annotation_id,
                "verification": verifier_id,
                "adjudication": adjudication_id,
                "judgments": JUDGMENT_A,
                "hash": "c" * 64,
                "now": NOW,
            },
        )
        repository_session = Session(bind=connection)
        try:
            summary = GoldRepository(repository_session).evidence_summary()
        finally:
            repository_session.close()
        assert summary.frozen_truth_count == 0
        assert summary.status == "NOT_OBSERVED"
        nested = connection.begin_nested()
        with pytest.raises(DBAPIError, match="immutable P9-B history"):
            connection.execute(
                text(
                    "update gold_truth_versions set revision_reason_code = 'REWRITE' "
                    "where gold_truth_version_id = :id"
                ),
                {"id": truth_id},
            )
        nested.rollback()
    finally:
        transaction.rollback()


def test_production_tables_do_not_reference_gold_truth(connection: Connection) -> None:
    rows = connection.execute(
        text(
            "select source.relname from pg_constraint constraint_row "
            "join pg_class source on source.oid = constraint_row.conrelid "
            "join pg_class target on target.oid = constraint_row.confrelid "
            "where constraint_row.contype = 'f' and target.relname like 'gold_%' "
            "and source.relname not like 'gold_%'"
        )
    ).scalars()

    assert list(rows) == []
