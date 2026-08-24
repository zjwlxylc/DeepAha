from pathlib import Path


def test_document_block_verifier_covers_gate_and_regression_boundaries() -> None:
    root = Path(__file__).parents[2]
    verifier = root / "scripts" / "verify-p9b-document-blocks.ps1"

    text = verifier.read_text(encoding="utf-8")

    assert "scripts/verify.ps1" in text.replace("\\", "/")
    assert "tests/documents/test_blocks.py" in text.replace("`\n", " ").replace("\\", "/")
    assert "tests/documents/test_docx_parser.py" in text.replace("`\n", " ").replace("\\", "/")
    assert "tests/integration/test_p9b_document_blocks.py" in text.replace("\\", "/")
    assert "tests/integration/test_p9b_document_block_migration.py" in text.replace("\\", "/")
    assert "tests/integration/test_document_service.py" in text.replace("\\", "/")
    assert "pytest -m integration --strict-markers" in text
    assert "alembic downgrade 20260824_0011" in text
    assert text.count("alembic check") >= 2
    assert "git diff --check" in text
    assert "down --volumes --remove-orphans" in text
