import json
from hashlib import sha256

import pytest

from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.reader import ReaderDocumentParser, replay_reader_anchor
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.evidence_verification.contracts import ArtifactInput
from deepaha.evidence_verification.verifier import EvidenceVerifier

URL = "https://example.gov/notice"


def artifact(body: str, title: str = "招聘公告") -> ArtifactInput:
    content = json.dumps(
        {"rows": [{"column2": title, "column11": "2026-08-11", "column13": body}]},
        ensure_ascii=False,
    ).encode()
    return ArtifactInput("notice", "application/json", URL, sha256(content).hexdigest(), content)


def test_notice_json_keeps_raw_hash_and_replayable_nested_html_origins() -> None:
    value = artifact("<p>学历：<span>本科</span></p><p>年龄：38周岁以下</p>")
    registry = default_registry()
    adapter = registry.select(value.media_type)
    assert adapter is not None
    parsed = ReaderDocumentParser(adapter).parse(value.content, artifact_sha256=value.sha256)
    block = next(b for b in parsed.blocks if b.canonical_text_or_value == "本科")
    projection = replay_reader_anchor(registry, value, block.structural_locator)
    spans = projection.source_spans(0, 2)
    assert spans is not None
    assert spans[0].origin_id.startswith("/rows/0/column13::")
    assert block.structural_locator["artifact_sha256"] == value.sha256
    check = EvidenceVerifier(registry).verify(value, "本科", {"url": URL})
    assert check.verdict == "PASS"


def test_json_pointer_scope_cannot_cross_fields_or_ignore_wrong_pointer() -> None:
    value = artifact("<p>本科</p>", title="本科")
    verifier = EvidenceVerifier(default_registry())
    assert verifier.verify(value, "本科", {"url": URL}).binding == "AMBIGUOUS"
    result = verifier.verify(value, "本科", {"json_pointer": "/rows/0/column13"})
    assert result.verdict == "PASS"
    assert verifier.verify(value, "本科", {"json_pointer": "/rows/0/missing"}).verdict == "FAIL"
    assert verifier.verify(value, "本科", {"url": "https://wrong.gov"}).verdict == "FAIL"


def test_replacement_characters_require_review_without_silently_repairing_title() -> None:
    value = artifact("<p>本科</p>", title="招\ufffd公告")
    adapter = default_registry().select(value.media_type)
    assert adapter is not None
    parsed = ReaderDocumentParser(adapter).parse(value.content, artifact_sha256=value.sha256)
    assert "READER_UNRELIABLE" in parsed.needs_review_reasons
    assert "招\ufffd公告" in parsed.normalized_text
    assert (
        EvidenceVerifier(default_registry()).verify(value, "本科", {"url": URL}).verdict
        == "UNVERIFIED"
    )


@pytest.mark.parametrize(
    "content",
    [
        b'{"rows":[],"rows":[{"column13":"<p>x</p>"}]}',
        b'{"rows":[{"column13":"<p>x</p>"},{"column13":"<p>y</p>"}]}',
        b'{"facts":[{"quote":"candidate only"}]}',
        b'{"rows":[{"column13":null}]}',
        b'{"rows":[{"column13":"<p>x</p>"}],"value":NaN}',
        b"\xff",
    ],
)
def test_unrecognized_or_ambiguous_json_is_rejected(content: bytes) -> None:
    adapter = default_registry().select("application/json")
    assert adapter is not None
    with pytest.raises(ExpectedParseError):
        adapter.read(content)
