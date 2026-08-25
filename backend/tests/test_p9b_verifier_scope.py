from pathlib import Path

ROOT = Path(__file__).parents[2]


def text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_replacement_compose_uses_only_dynamic_loopback_ports() -> None:
    compose = text("infra/compose.p9b.yaml")

    assert '"127.0.0.1::5432"' in compose
    assert '"127.0.0.1::5000"' in compose
    assert "55439" not in compose
    assert "55007" not in compose


def test_replacement_verifier_owns_isolated_projects_and_exact_cleanup() -> None:
    verifier = text("scripts/verify-p9b.ps1")

    for required in (
        "deepaha-p9b-replacement-",
        "$projectName-smoke-a",
        "$projectName-smoke-b",
        "Sort-Object -Unique",
        "down --volumes --remove-orphans",
        "cleanup was incomplete",
        "docker compose --project-name $Name --file $composeFile",
    ):
        assert required in verifier
    assert "55439" not in verifier
    assert "55007" not in verifier


def test_replacement_verifier_is_detached_head_compatible() -> None:
    verifier = text("scripts/verify-p9b.ps1")

    assert "git rev-parse HEAD" in verifier
    assert "symbolic-ref" not in verifier
    assert "branch --show-current" not in verifier
    assert "rev-parse --abbrev-ref" not in verifier


def test_replacement_verifier_runs_full_internal_checks_without_qualification() -> None:
    verifier = text("scripts/verify-p9b.ps1")

    for required in (
        "uv sync --locked --group dev",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run mypy src tests",
        "uv run pytest --strict-markers",
        "corepack pnpm install --frozen-lockfile",
        "corepack pnpm lint",
        "corepack pnpm typecheck",
        "corepack pnpm test",
        "corepack pnpm build",
        "uv run alembic upgrade head",
        "uv run pytest -m integration --strict-markers",
        "uv run alembic check",
        "uv run alembic downgrade 20260825_0028",
        "P9-B INTERNAL VERIFIER=PASS",
        "Independent Acceptance=NOT_RUN",
        "P9-B Engineering Gate=OPEN",
        "P9-B Release Qualification=NOT_STARTED",
        "P9-B Contract=IMPLEMENTED, not STABLE",
    ):
        assert required in verifier


def test_legacy_port_wrapper_occupies_fixed_ports_before_full_verifier() -> None:
    wrapper = text("scripts/verify-p9b-with-legacy-ports-occupied.ps1")

    assert "55439" in wrapper
    assert "55007" in wrapper
    assert "verify-p9b.ps1" in wrapper


def test_gateway_has_exactly_one_provider_invoke_call_site() -> None:
    source_files = tuple((ROOT / "backend/src/deepaha/p9b").rglob("*.py"))
    call_sites = [path for path in source_files if ".invoke(" in path.read_text(encoding="utf-8")]

    assert call_sites == [ROOT / "backend/src/deepaha/p9b/gateway.py"]
    assert text("backend/src/deepaha/p9b/gateway.py").count(".invoke(") == 1
