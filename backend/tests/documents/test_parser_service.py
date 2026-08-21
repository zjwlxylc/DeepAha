from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from deepaha.contracts.phase2 import HtmlSelectorLocator
from deepaha.documents.parser import ExpectedParseError, ParsedDocument


def parsed_document() -> ParsedDocument:
    text = "正式公告\n"
    return ParsedDocument(
        title="正式公告",
        published_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        language="zh-CN",
        normalized_text=text,
        locators=(
            HtmlSelectorLocator(
                schema_version="0.2.0",
                kind="html_selector",
                selector="main > p:nth-of-type(1)",
                text_sha256=sha256(text.encode()).hexdigest(),
            ),
        ),
        needs_review_reasons=(),
    )


def test_parsed_document_is_immutable() -> None:
    value = parsed_document()

    with pytest.raises(FrozenInstanceError):
        value.language = "und"  # type: ignore[misc]


def test_expected_parse_error_exposes_stable_code() -> None:
    error = ExpectedParseError("HTML_TEXT_EMPTY")

    assert error.code == "HTML_TEXT_EMPTY"
    assert str(error) == "HTML_TEXT_EMPTY"


@pytest.mark.parametrize("code", ["", "html_empty", "HTML EMPTY", "../FAILED"])
def test_expected_parse_error_rejects_unstable_codes(code: str) -> None:
    with pytest.raises(ValueError, match="stable uppercase code"):
        ExpectedParseError(code)
