from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]


def test_phase5_verifier_uses_only_its_isolated_project_and_ports() -> None:
    verifier = (REPOSITORY_ROOT / "scripts" / "verify-phase5.ps1").read_text("utf-8")
    compose = (REPOSITORY_ROOT / "infra" / "compose.phase5.yaml").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    assert "55435" in compose and "55003" in compose
    for required in (
        "compose_project_name",
        "deepaha-phase5-",
        "infra/compose.phase5.yaml",
        "finally",
        "down --volumes --remove-orphans",
    ):
        assert required in normalized
    for forbidden in (
        "55432",
        "55000",
        "55433",
        "55001",
        "55434",
        "55002",
        "deepaha-phase2-",
        "deepaha-phase3-",
        "deepaha-phase4-",
        "verify-phase1",
        "verify-phase2",
        "verify-phase3",
        "verify-phase4",
        "live_source",
    ):
        assert forbidden not in normalized


def test_phase5_verifier_covers_quality_contract_migration_and_web_checks() -> None:
    verifier = (REPOSITORY_ROOT / "scripts" / "verify-phase5.ps1").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    for required in (
        "scripts/verify.ps1",
        "tests/contracts",
        "tests/opportunities",
        "tests/public_catalog",
        "tests/api/test_public_opportunities.py",
        "tests/integration/test_phase5_public_catalog_persistence.py",
        "tests/integration/test_phase5_public_catalog_service.py",
        "tests/integration/test_phase5_public_api_read_only.py",
        "alembic upgrade head",
        "alembic downgrade 20260822_0004",
        "alembic check",
        "synthetic_fixture_only",
        "release qualification: not_started",
        "phase 5 public api contract maturity: implemented",
    ):
        assert required in normalized


def test_ci_has_phase5_branch_and_scoped_job() -> None:
    ci = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

    assert "codex/phase-5-public-trust-layer" in ci
    job = _phase5_job(ci)
    for required in (
        "phase5-public-trust:",
        '"55435:5432"',
        '"55003:5000"',
        "test_phase5_verifier_scope.py",
        "test_phase5_public_catalog_service.py",
        "test_phase5_public_api_read_only.py",
        "alembic downgrade 20260822_0004",
        "alembic check",
    ):
        assert required in job
    for forbidden in (
        "55432",
        "55000",
        "55433",
        "55001",
        "55434",
        "55002",
        "live_source",
    ):
        assert forbidden not in job.lower()


def _phase5_job(ci: str) -> str:
    start = ci.index("  phase5-public-trust:")
    return ci[start:]
