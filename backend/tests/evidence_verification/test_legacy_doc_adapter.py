import subprocess
from hashlib import sha256
from unittest.mock import patch

import pytest

from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.reader import ReaderDocumentParser, replay_reader_anchor
from deepaha.evidence_verification.adapters.legacy_doc import LegacyDocAdapter, convert_doc
from deepaha.evidence_verification.contracts import ArtifactInput
from deepaha.evidence_verification.registry import AdapterRegistry
from deepaha.evidence_verification.verifier import EvidenceVerifier

IMAGE = "sha256:" + "1" * 64
RAW = bytes.fromhex("d0cf11e0a1b11ae1") + bytes(504)
XML = b"<book><chapter><para>Degree: <emphasis>doctorate</emphasis>.</para></chapter></book>"


def test_doc_conversion_replays_from_raw_bytes_but_requires_human_layout_check() -> None:
    adapter = LegacyDocAdapter(IMAGE)
    registry = AdapterRegistry((adapter,))
    artifact = ArtifactInput(
        "guide", "application/msword", "https://example.gov/guide", sha256(RAW).hexdigest(), RAW
    )
    with patch("deepaha.evidence_verification.adapters.legacy_doc.convert_doc", return_value=XML):
        parsed = ReaderDocumentParser(adapter).parse(RAW, artifact_sha256=artifact.sha256)
        assert parsed.normalized_text == "Degree: doctorate."
        assert not parsed.needs_review_reasons
        projection = replay_reader_anchor(registry, artifact, parsed.blocks[0].structural_locator)
        assert projection.text == "Degree: doctorate."
        result = EvidenceVerifier(registry).verify(
            artifact, "doctorate", {"url": artifact.source_url}
        )
        assert result.content_support == "FOUND"
        assert result.verdict == "UNVERIFIED"


@pytest.mark.parametrize("raw", [b"not word", b"PK" + bytes(510)])
def test_invalid_doc_never_starts_converter(raw: bytes) -> None:
    with patch("deepaha.evidence_verification.adapters.legacy_doc.convert_doc") as convert:
        with pytest.raises(ExpectedParseError, match="DOC_SIGNATURE_INVALID"):
            LegacyDocAdapter(IMAGE).read(raw)
        convert.assert_not_called()


@pytest.mark.parametrize(
    "xml",
    [b"<book><para>&bad;</para></book>", b"<html>error</html>", b"<book><imageobject/></book>"],
)
def test_invalid_or_unread_content_is_not_silently_accepted(xml: bytes) -> None:
    with (
        patch("deepaha.evidence_verification.adapters.legacy_doc.convert_doc", return_value=xml),
        pytest.raises(ExpectedParseError),
    ):
        LegacyDocAdapter(IMAGE).read(RAW)


def test_converter_only_accepts_immutable_image_id() -> None:
    with pytest.raises(ValueError):
        LegacyDocAdapter("untrusted/image:latest")


def test_timeout_removes_only_its_own_container_and_returns_stable_error() -> None:
    with (
        patch(
            "deepaha.evidence_verification.adapters.legacy_doc.subprocess.run",
            side_effect=[
                subprocess.TimeoutExpired("docker", 30),
                subprocess.CompletedProcess([], 0),
            ],
        ) as run,
        pytest.raises(ExpectedParseError, match="DOC_READER_TIMEOUT"),
    ):
        convert_doc(RAW, IMAGE)
    command = run.call_args_list[0].args[0]
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--pull") + 1] == "never"
    assert "--read-only" in command and "--privileged" not in command
    assert command[-4:] == [IMAGE, "-x", "db", "-"]
    name = command[command.index("--name") + 1]
    assert name.startswith("deepaha-doc-read-")
    assert run.call_args_list[1].args[0] == ["docker", "rm", "--force", name]


def test_missing_converter_returns_stable_error() -> None:
    with (
        patch(
            "deepaha.evidence_verification.adapters.legacy_doc.subprocess.run",
            side_effect=FileNotFoundError,
        ),
        pytest.raises(ExpectedParseError, match="DOC_READER_UNAVAILABLE"),
    ):
        convert_doc(RAW, IMAGE)
