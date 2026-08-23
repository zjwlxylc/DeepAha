from hashlib import sha256

import pytest

from deepaha.documents.normalization import build_derived_text_key, normalize_text


def test_normalize_text_is_conservative() -> None:
    assert normalize_text("标题  \r\n\r\n\r\n日期：2026-08-21\t \r\n") == (
        "标题\n\n日期：2026-08-21\n"
    )


def test_normalize_text_uses_unicode_nfc_without_rewriting_words() -> None:
    decomposed = "Cafe\u0301 2026/08/21"

    assert normalize_text(decomposed) == "Café 2026/08/21"


def test_derived_key_never_uses_raw_namespace() -> None:
    digest = "a" * 64

    key = build_derived_text_key(digest, "html_lxml", "0.2.0")

    assert key == f"derived/documents/{digest}/html_lxml/0.2.0/text.txt"
    assert not key.startswith("raw/")


@pytest.mark.parametrize("component", ["HTML", "html/lxml", "../html", "html lxml", ""])
def test_derived_key_rejects_unsafe_parser_components(component: str) -> None:
    with pytest.raises(ValueError, match="parser name and version"):
        build_derived_text_key(sha256(b"raw").hexdigest(), component, "0.2.0")


def test_derived_key_requires_sha256() -> None:
    with pytest.raises(ValueError, match="artifact SHA-256"):
        build_derived_text_key("not-a-digest", "html_lxml", "0.2.0")
