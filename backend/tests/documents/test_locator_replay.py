from hashlib import sha256
from pathlib import Path

import pytest

from deepaha.contracts.phase2 import HtmlSelectorLocator
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.locator import LocatorReplayError, replay_html_locator

FIXTURE = Path(__file__).parents[1] / "fixtures" / "documents" / "minimal-official.html"


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
