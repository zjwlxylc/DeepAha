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
)
PRIOR_PROJECTS = tuple(f"deepaha-phase{phase}-" for phase in range(2, 8))


def _phase8_verifier() -> str:
    return (REPOSITORY_ROOT / "scripts" / "verify-phase8.ps1").read_text("utf-8")


def test_phase8_verifier_uses_only_exact_isolated_project_and_ports() -> None:
    verifier = _phase8_verifier()
    compose = (REPOSITORY_ROOT / "infra" / "compose.phase8.yaml").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    assert "55438" in compose and "55006" in compose
    for required in (
        "compose_project_name",
        "deepaha-phase8-",
        "^deepaha-phase8-[a-z0-9][a-z0-9-]*$",
        "infra/compose.phase8.yaml",
        "docker compose --project-name $projectname --file $composefile ps -q",
        "assert-portavailableorowned 55438",
        "assert-portavailableorowned 55006",
        "finally",
        "down --volumes --remove-orphans",
    ):
        assert required in normalized
    assert normalized.index("assert-portavailableorowned 55438") < normalized.index("up -d --wait")
    assert normalized.index("assert-portavailableorowned 55006") < normalized.index("up -d --wait")
    for variable in (
        "deepaha_database_url",
        "deepaha_object_store_endpoint",
        "deepaha_object_store_region",
        "deepaha_object_store_bucket",
        "deepaha_object_store_access_key",
        "deepaha_object_store_secret_key",
        "deepaha_environment",
        "deepaha_personal_auth_mode",
    ):
        assert f"remove-item env:{variable}" in normalized
    for forbidden in (
        *PRIOR_PORTS,
        *PRIOR_PROJECTS,
        "docker system prune",
        "live_source",
        "record_human_run",
        "humanvalidationrunwrite",
        "openai",
        "anthropic",
    ):
        assert forbidden not in normalized


def test_phase8_verifier_covers_contracts_runtime_integrations_and_boundaries() -> None:
    normalized = _phase8_verifier().replace("\\", "/").lower()

    for required in (
        "scripts/verify.ps1",
        "tests/contracts/test_phase8_contracts.py",
        "tests/notifications",
        "tests/api/test_reminders.py",
        "tests/test_phase8_verifier_scope.py",
        "tests/integration/test_phase8_candidate_transaction.py",
        "tests/integration/test_phase8_inbox_isolation.py",
        "tests/integration/test_phase8_persistence.py",
        "tests/integration/test_phase8_preference_api.py",
        "tests/integration/test_phase8_public_governance.py",
        "tests/integration/test_phase8_transaction_rollback.py",
        "tests/integration/test_phase8_vertical_slice.py",
        "tests/integration/test_phase8_worker_recovery.py",
        "tests.notifications.seed_phase8_browser",
        "priorpythonpath",
        '$env:pythonpath = "src"',
        "$env:pythonpath = $priorpythonpath",
        "remove-item env:pythonpath",
        "alembic upgrade head",
        "alembic downgrade 20260822_0007",
        "alembic check",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test",
        "pnpm build",
        "synthetic_reminder_delivery_only",
        "real participants=0",
        "human track=not_started",
        "release qualification=not_started",
        "release decision=hold_missing_human_evidence",
        "delivery target=test_inbox",
    ):
        assert required in normalized


def test_ci_keeps_inherited_jobs_and_adds_scoped_phase8_job() -> None:
    ci = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

    for inherited in (
        "backend-quality:",
        "web-quality:",
        "integration:",
        "phase3-resolution:",
        "phase4-eligibility:",
        "phase5-public-trust:",
        "phase6-profile-action:",
        "phase7-feedback-review:",
    ):
        assert f"  {inherited}" in ci
    assert "codex/phase-8-deadline-change-reminders" in ci
    job = ci[ci.index("  phase8-deadline-reminder:") :]
    for required in (
        '"55438:5432"',
        '"55006:5000"',
        "deepaha_phase8_local_only",
        'python-version: "3.14"',
        'node-version: "24"',
        "test_phase8_verifier_scope.py",
        "test_phase8_candidate_transaction.py",
        "test_phase8_inbox_isolation.py",
        "test_phase8_persistence.py",
        "test_phase8_preference_api.py",
        "test_phase8_public_governance.py",
        "test_phase8_transaction_rollback.py",
        "test_phase8_vertical_slice.py",
        "test_phase8_worker_recovery.py",
        "tests.notifications.seed_phase8_browser",
        "PYTHONPATH: src",
        "alembic downgrade 20260822_0007",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test",
        "pnpm build",
    ):
        assert required in job
    for forbidden in (*PRIOR_PORTS, *PRIOR_PROJECTS, "live_source"):
        assert forbidden not in job.lower()
