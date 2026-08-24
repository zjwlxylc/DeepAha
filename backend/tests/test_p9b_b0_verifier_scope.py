from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]


def verifier_text() -> str:
    return (REPOSITORY_ROOT / "scripts" / "verify-p9b-b0.ps1").read_text("utf-8")


def test_b0_verifier_is_isolated_and_covers_required_gates() -> None:
    normalized = verifier_text().replace("\\", "/").lower()

    for required in (
        "^deepaha-p9b-b0-[a-z0-9][a-z0-9-]*$",
        "infra/compose.source-acquisition.yaml",
        "55439",
        "55007",
        "scripts/verify.ps1",
        "tests/contracts/test_phase9b_contracts.py",
        "tests/p9b",
        "tests/integration/test_p9b_b0_migration.py",
        "tests/integration/test_p9b_b0_persistence.py",
        "tests/integration/test_document_service.py",
        "pytest -m integration",
        "alembic check",
        "alembic downgrade 20260823_0010",
        "alembic upgrade head",
        "down --volumes --remove-orphans",
    ):
        assert required in normalized


def test_b0_verifier_does_not_start_release_qualification() -> None:
    normalized = verifier_text().lower()

    assert "run-source-acquisition-qualification.ps1" not in normalized
    assert "release qualification" not in normalized
