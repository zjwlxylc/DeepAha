from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
PRIOR_PORTS = (
    "55432",
    "55000",
    "55433",
    "55001",
    "55434",
    "55002",
    "55435",
    "55003",
    "55436",
    "55004",
    "55437",
    "55005",
    "55438",
    "55006",
)


def _verifier() -> str:
    return (REPOSITORY_ROOT / "scripts" / "verify-source-acquisition-platform.ps1").read_text(
        "utf-8"
    )


def test_verifier_uses_an_exact_isolated_project_and_cleans_it() -> None:
    verifier = _verifier()
    compose = (REPOSITORY_ROOT / "infra" / "compose.source-acquisition.yaml").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    assert "55439" in compose and "55007" in compose
    for required in (
        "compose_project_name",
        "deepaha-source-acquisition-",
        "^deepaha-source-acquisition-[a-z0-9][a-z0-9-]*$",
        "infra/compose.source-acquisition.yaml",
        "docker compose --project-name $projectname --file $composefile ps -q",
        "assert-portavailableorowned 55439",
        "assert-portavailableorowned 55007",
        "finally",
        "down --volumes --remove-orphans",
    ):
        assert required in normalized
    for port in PRIOR_PORTS:
        assert f"assert-portavailableorowned {port}" not in normalized
    for variable in (
        "deepaha_database_url",
        "deepaha_object_store_endpoint",
        "deepaha_object_store_region",
        "deepaha_object_store_bucket",
        "deepaha_object_store_access_key",
        "deepaha_object_store_secret_key",
        "deepaha_environment",
        "deepaha_real_source_corpus_root",
        "deepaha_real_source_corpus_backend",
    ):
        assert f"remove-item env:{variable}" in normalized


def test_verifier_covers_historical_gates_p9a_replay_migrations_and_scope() -> None:
    normalized = _verifier().replace("\\", "/").lower()

    for required in (
        "scripts/verify.ps1",
        "scripts/verify-phase2.ps1",
        "scripts/verify-phase8.ps1",
        "tests/acquisition",
        "tests/sources/test_registry_manifest.py",
        "tests/sources/test_official_source_manifest.py",
        "tests/test_source_acquisition_verifier_scope.py",
        "tests/integration/test_acquisition_document_gate.py",
        "tests/integration/test_acquisition_evaluation_persistence.py",
        "tests/integration/test_acquisition_evaluation_service.py",
        "tests/integration/test_acquisition_fetchers.py",
        "tests/integration/test_acquisition_health_migration.py",
        "tests/integration/test_acquisition_health_persistence.py",
        "tests/integration/test_acquisition_health.py",
        "tests/integration/test_acquisition_migration.py",
        "tests/integration/test_acquisition_orchestrator.py",
        "tests/integration/test_real_acquisition_replay.py",
        "tests/integration/test_real_s02_opportunity_replay.py",
        "tests/integration/test_real_integration_cost_gate.py",
        "deepaha_real_source_corpus_root",
        "alembic upgrade head",
        "alembic downgrade 20260822_0008",
        "alembic check",
        "ruff check",
        "mypy src/deepaha/acquisition",
        "git diff --check",
        "source acquisition platform engineering gate=closed",
        "release qualification=not_started",
        "100-source/14-day target=not_run",
    ):
        assert required in normalized


def test_default_verifier_has_no_live_network_or_qualification_mode() -> None:
    normalized = _verifier().replace("\\", "/").lower()

    for forbidden in (
        "deepaha_allow_live_source_check",
        "--live",
        "live_source",
        "run-source-acquisition-qualification.ps1",
        "playwright",
        "captcha solving",
        "docker system prune",
    ):
        assert forbidden not in normalized
