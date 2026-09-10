"""Keep coverage anchors while avoiding repeated expensive CI work."""

from pathlib import Path

CI = (Path(__file__).parents[2] / ".github/workflows/ci.yml").read_text("utf-8")


def test_ci_runs_shared_suites_once() -> None:
    assert CI.count("- run: uv run pytest -m integration --strict-markers") == 1
    for command in ("pnpm test", "pnpm build", "pnpm lint", "pnpm typecheck"):
        assert CI.count(f"- run: {command}\n") == 1
    for command in ("uv run ruff format --check .", "uv run ruff check .", "uv run mypy src tests"):
        assert CI.count(f"- run: {command}\n") == 1
    assert "uv run --extra wma pytest" in CI


def test_ci_keeps_unique_phase_and_browser_checks() -> None:
    for revision in range(3, 8):
        assert f"alembic downgrade 20260822_{revision:04}" in CI
    for config in ("playwright.investigations.config.ts", "playwright.relations.config.ts"):
        assert f"playwright test --config {config}" in CI
    assert "playwright test e2e/phase8-reminder.spec.ts" in CI
    assert "tests/notifications" in CI and "tests/integration/test_phase8_worker_recovery.py" in CI


def test_phase8_uses_same_run_build_and_no_rebuild() -> None:
    phase8 = CI.split("  phase8-deadline-reminder:")[1]
    assert "needs: web-quality" in phase8
    assert "actions/download-artifact@" in phase8
    assert "next-build-${{ github.sha }}" in phase8
    assert "pnpm build" not in phase8
    assert "overwrite: true" in CI
    assert "github.run_attempt" not in CI
    assert "retention-days: 1" in CI
    assert "if-no-files-found: error" in CI


def test_only_superseded_pr_runs_are_cancelled() -> None:
    group = "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
    assert group in CI
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in CI
    assert "paths-ignore:" not in CI and "paths:" not in CI
