from hashlib import sha256

import pytest

from deepaha.contracts.phase2 import HtmlSelectorLocator
from deepaha.documents.html import LxmlHtmlParser, P9BHtmlDocumentParser
from deepaha.documents.locator import replay_html_locator
from deepaha.documents.parser import ExpectedParseError


def test_utf8_fragment_preserves_chinese_block_and_inline_quote() -> None:
    content = '<p id="degree">报考要求：<strong>本科</strong>及以上。</p>'.encode()
    parsed = P9BHtmlDocumentParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    assert parsed.blocks[0].canonical_text_or_value == "报考要求：本科及以上。"
    assert parsed.needs_review_reasons == ()
    assert P9BHtmlDocumentParser.version != "0.8.0"


@pytest.mark.parametrize(
    ("header", "encoding", "text"),
    [
        ('<meta charset="gbk">', "gbk", "本科及以上"),
        ('<meta http-equiv="Content-Type" content="text/html; charset=GB2312">', "gb2312", "学历"),
        ('<meta charset="windows-1252">', "cp1252", "Café"),
        # The bytes are valid UTF-8 too. An explicit declaration still wins.
        ('<meta charset="iso-8859-1">', "latin1", "CafÃ©"),
    ],
)
def test_declared_encoding_is_not_overridden(header: str, encoding: str, text: str) -> None:
    content = f"<html><head>{header}</head><body><p>{text}</p></body></html>".encode(encoding)
    parsed = P9BHtmlDocumentParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    assert parsed.blocks[0].canonical_text_or_value == text


def test_undeclared_non_utf8_bytes_require_encoding_review() -> None:
    content = "<p>本科及以上</p>".encode("gbk")
    with pytest.raises(ExpectedParseError, match="HTML_ENCODING_UNRESOLVED"):
        P9BHtmlDocumentParser().parse(content, artifact_sha256=sha256(content).hexdigest())


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-32"])
def test_byte_order_mark_is_preserved(encoding: str) -> None:
    content = "<p>本科及以上</p>".encode(encoding)
    parsed = P9BHtmlDocumentParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    assert parsed.blocks[0].canonical_text_or_value == "本科及以上"


def test_legacy_parser_and_legacy_locator_replay_keep_historical_behavior() -> None:
    content = "<p>本科及以上</p>".encode()
    parsed = LxmlHtmlParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    assert LxmlHtmlParser.version == "0.2.0"
    assert parsed.blocks == ()
    assert parsed.normalized_text == (
        "\u00e6\u009c\u00ac\u00e7\u00a7\u0091\u00e5\u008f\u008a"
        "\u00e4\u00bb\u00a5\u00e4\u00b8\u008a\n"
    )
    locator = parsed.locators[0]
    assert isinstance(locator, HtmlSelectorLocator)
    assert replay_html_locator(content, locator) == parsed.normalized_text.strip()
