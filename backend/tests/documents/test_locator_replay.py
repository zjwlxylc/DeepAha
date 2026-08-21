from hashlib import sha256
from pathlib import Path

import pytest

from deepaha.contracts.phase2 import HtmlSelectorLocator, PdfPageTextLocator
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.locator import (
    LocatorReplayError,
    replay_html_locator,
    replay_pdf_locator,
)
from deepaha.documents.pdf import PypdfDocumentParser

FIXTURES = Path(__file__).parents[1] / "fixtures" / "documents"
FIXTURE = FIXTURES / "minimal-official.html"
TEXT_PDF = FIXTURES / "minimal-text.pdf"


def test_html_locators_replay_hash() -> None:
    content = FIXTURE.read_bytes()
    parsed = LxmlHtmlParser().parse(content, artifact_sha256=sha256(content).hexdigest())

    for locator in parsed.locators:
        assert isinstance(locator, HtmlSelectorLocator)
        text = replay_html_locator(content, locator)
        assert sha256(text.encode()).hexdigest() == locator.text_sha256


def test_html_locator_replay_detects_changed_content() -> None:
    content = FIXTURE.read_bytes()
    parsed = LxmlHtmlParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    changed = content.replace("报名日期：2026-08-21".encode(), "报名日期：2026-08-22".encode())
    locator = parsed.locators[1]
    assert isinstance(locator, HtmlSelectorLocator)

    with pytest.raises(LocatorReplayError, match="hash mismatch"):
        replay_html_locator(changed, locator)


def test_html_locator_replay_requires_one_matching_node() -> None:
    content = FIXTURE.read_bytes()
    parsed = LxmlHtmlParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    locator = parsed.locators[0]
    assert isinstance(locator, HtmlSelectorLocator)
    missing = locator.model_copy(update={"selector": "html > body > aside"})

    with pytest.raises(LocatorReplayError, match="exactly one node"):
        replay_html_locator(content, missing)


def test_pdf_locator_replays_page_text() -> None:
    content = TEXT_PDF.read_bytes()
    parsed = PypdfDocumentParser().parse(
        content,
        artifact_sha256=sha256(content).hexdigest(),
    )

    assert all(isinstance(locator, PdfPageTextLocator) for locator in parsed.locators)
    pdf_locators = [
        locator for locator in parsed.locators if isinstance(locator, PdfPageTextLocator)
    ]
    assert {locator.page_number for locator in pdf_locators} == {1, 2}
    for locator in pdf_locators:
        text = replay_pdf_locator(content, locator)
        assert sha256(text.encode()).hexdigest() == locator.text_sha256


def test_pdf_locator_rejects_zero_based_page() -> None:
    content = TEXT_PDF.read_bytes()
    parsed = PypdfDocumentParser().parse(
        content,
        artifact_sha256=sha256(content).hexdigest(),
    )
    original = parsed.locators[0]
    assert isinstance(original, PdfPageTextLocator)
    locator = original.model_copy(update={"page_number": 0})

    with pytest.raises(LocatorReplayError, match="1-based"):
        replay_pdf_locator(content, locator)


def test_pdf_locator_replay_detects_hash_mismatch() -> None:
    content = TEXT_PDF.read_bytes()
    parsed = PypdfDocumentParser().parse(
        content,
        artifact_sha256=sha256(content).hexdigest(),
    )
    original = parsed.locators[0]
    assert isinstance(original, PdfPageTextLocator)
    locator = original.model_copy(update={"text_sha256": "0" * 64})

    with pytest.raises(LocatorReplayError, match="hash mismatch"):
        replay_pdf_locator(content, locator)
