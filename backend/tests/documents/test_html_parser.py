from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

import pytest

from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.parser import ExpectedParseError

FIXTURES = Path(__file__).parents[1] / "fixtures" / "documents"
MINIMAL = FIXTURES / "minimal-official.html"
EMPTY = FIXTURES / "empty-body.html"


def parse(content: bytes):  # type: ignore[no-untyped-def]
    return LxmlHtmlParser().parse(content, artifact_sha256=sha256(content).hexdigest())


def test_html_parser_extracts_only_the_single_main_body() -> None:
    parsed = parse(MINIMAL.read_bytes())

    assert parsed.title == "青年机会公告"
    assert parsed.published_at is None
    assert parsed.language == "zh-CN"
    assert parsed.normalized_text == (
        "青年机会公告\n\n报名日期：2026-08-21\n\n申请材料 以原文为准。\n"
    )
    assert parsed.needs_review_reasons == ()
    assert [locator.selector for locator in parsed.locators] == [
        "html:nth-of-type(1) > body:nth-of-type(1) > main:nth-of-type(1) "
        "> article:nth-of-type(1) > h1:nth-of-type(1)",
        "html:nth-of-type(1) > body:nth-of-type(1) > main:nth-of-type(1) "
        "> article:nth-of-type(1) > p:nth-of-type(1)",
        "html:nth-of-type(1) > body:nth-of-type(1) > main:nth-of-type(1) "
        "> article:nth-of-type(1) > p:nth-of-type(2)",
    ]
    assert all("#" not in value.selector and "." not in value.selector for value in parsed.locators)
    assert "页眉" not in parsed.normalized_text
    assert "不得进入正文" not in parsed.normalized_text


def test_html_parser_supports_only_html_media_type() -> None:
    parser = LxmlHtmlParser()

    assert parser.name == "html_lxml"
    assert parser.version == "0.2.0"
    assert parser.supports("text/html") is True
    assert parser.supports("text/html; charset=utf-8") is True
    assert parser.supports("application/pdf") is False


def test_body_fallback_and_invalid_language() -> None:
    content = (
        b"<html lang='not_valid!'><head><title> Body title </title></head>"
        b"<body><section><p>Body only</p></section></body></html>"
    )

    parsed = parse(content)

    assert parsed.title == "Body title"
    assert parsed.language == "und"
    assert parsed.normalized_text == "Body only\n"


def test_single_article_is_used_when_main_is_ambiguous() -> None:
    content = (
        b"<html><body><main><p>First main</p></main><main><p>Second main</p></main>"
        b"<article><p>Unique article</p></article></body></html>"
    )

    assert parse(content).normalized_text == "Unique article\n"


def test_blank_html_is_an_expected_stable_failure() -> None:
    content = EMPTY.read_bytes()

    with pytest.raises(ExpectedParseError) as captured:
        parse(content)

    assert captured.value.code == "HTML_TEXT_EMPTY"


def test_malformed_html_recovery_is_deterministic() -> None:
    content = b"<html lang='en'><head><title>Broken</title></head><body><main><p>One<p>Two"

    first = parse(content)
    second = parse(content)

    assert first.normalized_text == "One\n\nTwo\n"
    assert asdict(first) == asdict(second)


def test_artifact_digest_mismatch_is_a_programmer_error() -> None:
    with pytest.raises(ValueError, match="artifact SHA-256"):
        LxmlHtmlParser().parse(MINIMAL.read_bytes(), artifact_sha256="0" * 64)


def test_external_entity_is_not_loaded(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("LOCAL_SECRET_MUST_NOT_LOAD", encoding="utf-8")
    uri = secret.as_uri()
    content = (
        f'<!DOCTYPE html [<!ENTITY external SYSTEM "{uri}">]>'
        "<html><body><main><p>&external;</p><p>Safe text</p></main></body></html>"
    ).encode()

    parsed = parse(content)

    assert "LOCAL_SECRET_MUST_NOT_LOAD" not in parsed.normalized_text
    assert "Safe text" in parsed.normalized_text
