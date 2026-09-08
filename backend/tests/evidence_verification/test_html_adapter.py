from hashlib import sha256

import pytest

from deepaha.evidence_verification.adapters.html import HtmlAdapter
from deepaha.evidence_verification.contracts import ArtifactInput, VerificationResult
from deepaha.evidence_verification.registry import AdapterRegistry
from deepaha.evidence_verification.verifier import EvidenceVerifier


def check(text: str, quote: str, locator: dict[str, object]) -> VerificationResult:
    content = text.encode()
    return EvidenceVerifier(AdapterRegistry((HtmlAdapter(),))).verify(
        ArtifactInput(
            "notice", "text/html", "https://example.gov/1", sha256(content).hexdigest(), content
        ),
        quote,
        locator,
    )


def test_cell_wrap_and_inline_scope_keep_original_node_offsets() -> None:
    text = '<table><tr><td id="a"><p>学历、学</p><p>位要求</p></td></tr></table>'
    result = check(text, "学历、学位要求", {"selector": "#a"})
    assert (result.verdict, result.content_support, result.binding) == ("PASS", "FOUND", "BOUND")
    sources = result.matches[0].source_spans
    assert len(sources) == 2
    assert sources[0].origin_id.endswith("/p[1]::text")
    assert sources[1].origin_id.endswith("/p[2]::text")
    assert (sources[0].start, sources[0].end, sources[1].start, sources[1].end) == (0, 4, 0, 3)
    inline = check(
        '<p>发布时间：<span id="date">2026-09-08</span></p>', "2026-09-08", {"selector": "#date"}
    )
    assert inline.verdict == "PASS"
    assert inline.matches[0].source_spans[0].origin_id.endswith("/span::text")


@pytest.mark.parametrize(
    "text,quote,selector",
    [
        ("<p>不得报名</p>", "可以报名", "p"),
        ("<p>学历、学 位要求</p>", "学历、学位要求", "p"),
        ("<table><tr><td>学历、学</td><td>位要求</td></tr></table>", "学历、学位要求", "tr"),
        ("<div><p>学历、学</p><p>位要求</p></div>", "学历、学位要求", "div"),
        ("<td><p>学历、学 </p><p>位要求</p></td>", "学历、学位要求", "td"),
        ("<td><p>学</p><div>位</div></td>", "学位", "td"),
        ("<p>2026-09-08</p>", "2026-09-09", "p"),
        ("<p>not eligible</p>", "noteligible", "p"),
        ("<p>Ａ</p>", "A", "p"),
    ],
)
def test_normalization_cannot_erase_original_or_structural_boundaries(
    text: str, quote: str, selector: str
) -> None:
    assert check(text, quote, {"selector": selector}).verdict == "FAIL"


@pytest.mark.parametrize(
    "text,quote",
    [
        ("<p>学<span>历</span>要求</p>", "学历要求"),
        ("<p>学\u200b\ufeff历\r\n\t 要求</p>", "学历 要求"),
        ("<p>学&nbsp;历</p>", "学 历"),
        ("<p>学<!-- annotation -->历</p>", "学历"),
    ],
)
def test_only_registered_representation_differences_pass(text: str, quote: str) -> None:
    assert check(text, quote, {"selector": "p"}).verdict == "PASS"


def test_ancestor_and_leaf_projections_of_same_source_do_not_create_ambiguity() -> None:
    result = check("<div><p>doctorate</p></div>", "doctorate", {"selector": "div, p"})
    assert result.verdict == "PASS"
    assert len(result.matches) == 1


def test_distinct_equal_cells_are_ambiguous_without_choosing_first() -> None:
    result = check(
        "<table><tr><td>doctorate</td><td>doctorate</td></tr></table>",
        "doctorate",
        {"selector": "td"},
    )
    assert result.verdict == "UNVERIFIED"
    assert result.binding == "AMBIGUOUS"
    assert len(result.matches) == 2


@pytest.mark.parametrize(
    "locator", [{"selector": "#absent"}, {"url": "https://wrong.gov"}, {"selector": "["}]
)
def test_wrong_declared_locator_is_not_rescued_by_artifact_search(
    locator: dict[str, object],
) -> None:
    assert check("<p>doctorate</p>", "doctorate", locator).verdict == "FAIL"


def test_human_requirement_is_preserved_even_with_machine_readable_scope() -> None:
    result = check("<p>doctorate</p>", "doctorate", {"selector": "p", "human_verify": True})
    assert result.content_support == "FOUND"
    assert result.declared_locator == "VERIFIED"
    assert result.verdict == "UNVERIFIED"


def test_expansion_limit_never_returns_a_partial_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deepaha.evidence_verification.adapters.html.MAX_PROJECTION_CHARACTERS", 10)
    result = check("<div><p>doctorate</p><p>another</p></div>", "doctorate", {"selector": "p"})
    assert result.verdict == "UNVERIFIED"
    assert result.reason_codes == ("READER_HTML_PROJECTION_LIMIT_EXCEEDED",)


def test_parser_depth_truncation_cannot_prove_locator_mismatch() -> None:
    text = "<div>" * 300 + '<p id="target">doctorate</p>' + "</div>" * 300
    result = check(text, "doctorate", {"selector": "#target"})
    assert result.verdict == "UNVERIFIED"
    assert result.reason_codes == ("READER_HTML_READING_INCOMPLETE",)


@pytest.mark.parametrize("empty", ["\ufeff ", "\ufeff\t", " \ufeff ", "\ufeff\ufeff\r\n"])
def test_empty_bom_paragraph_cannot_abort_an_unrelated_valid_scope(empty: str) -> None:
    result = check(
        f'<p>{empty}</p><p id="target">doctorate</p>', "doctorate", {"selector": "#target"}
    )
    assert result.verdict == "PASS"
