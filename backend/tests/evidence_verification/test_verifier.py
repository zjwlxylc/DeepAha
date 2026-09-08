from dataclasses import replace
from hashlib import sha256

import pytest

from deepaha.documents.parser import ExpectedParseError
from deepaha.evidence_verification.contracts import (
    ArtifactInput,
    Projection,
    ProjectionRun,
    ReaderIdentity,
    Representation,
    ScopeResolution,
    SourceSpan,
)
from deepaha.evidence_verification.registry import AdapterRegistry
from deepaha.evidence_verification.verifier import EvidenceVerifier

IDENTITY = ReaderIdentity("synthetic-text", "1", "synthetic-reader/1", "literal/1")


class SyntheticAdapter:
    """A local test reader, never a production format or a fact producer."""

    identity = IDENTITY
    media_types = ("application/x-deepaha-synthetic-text",)

    def __init__(self, *, complete: bool = True, reliable: bool = True) -> None:
        self.reads = 0
        self.complete = complete
        self.reliable = reliable

    def normalize_quote(self, quote: str) -> str:
        return quote

    def read(self, content: bytes) -> Representation:
        self.reads += 1
        projections = []
        for number, line in enumerate(content.decode().splitlines(), 1):
            if line:
                projections.append(
                    Projection(
                        str(number),
                        line,
                        (
                            ProjectionRun(
                                0, len(line), (SourceSpan(f"line:{number}", 0, len(line)),)
                            ),
                        ),
                    )
                )
        return Representation(
            self.identity,
            sha256(content).hexdigest(),
            tuple(projections),
            complete=self.complete,
            reliable=self.reliable,
        )

    def resolve_scope(
        self, representation: Representation, locator: dict[str, object], *, source_url: str
    ) -> ScopeResolution:
        del source_url
        ids = tuple(p.projection_id for p in representation.projections)
        if not locator:
            return ScopeResolution("UNBOUND", ids, "ARTIFACT")
        if set(locator) == {"line"} and type(locator["line"]) is int:
            target = str(locator["line"])
            return ScopeResolution("VERIFIED" if target in ids else "MISMATCH", (target,), "SCOPE")
        return ScopeResolution("UNSUPPORTED", ids, "ARTIFACT")


def artifact(text: str = "Eligible: doctorate.\nIneligible: master.") -> ArtifactInput:
    content = text.encode()
    return ArtifactInput(
        "notice",
        SyntheticAdapter.media_types[0],
        "https://example.gov/1",
        sha256(content).hexdigest(),
        content,
    )


def engine(adapter: SyntheticAdapter | None = None) -> EvidenceVerifier:
    return EvidenceVerifier(AdapterRegistry((adapter or SyntheticAdapter(),)))


def test_literal_content_and_declared_scope_can_pass_without_approving_a_fact() -> None:
    result = engine().verify(artifact(), "doctorate", {"line": 1})
    assert result.verdict == "PASS"
    assert result.content_support == "FOUND"
    assert result.declared_locator == "VERIFIED"
    assert result.binding == "BOUND"
    assert result.precision == "SCOPE"
    assert result.matches[0].source_spans == (SourceSpan("line:1", 10, 19),)
    assert result.reader == IDENTITY
    assert len(result.representation_sha256 or "") == 64


def test_wrong_artifact_hash_fails_before_the_reader_runs() -> None:
    reader = SyntheticAdapter()
    source = artifact()
    source = ArtifactInput(
        source.artifact_id, source.media_type, source.source_url, "0" * 64, source.content
    )
    result = engine(reader).verify(source, "doctorate", {"line": 1})
    assert result.verdict == "FAIL"
    assert result.reason_codes == ("ARTIFACT_HASH_MISMATCH",)
    assert reader.reads == 0


@pytest.mark.parametrize("quote", ["master", "Doctorate", "doctorate or master", "eligible"])
def test_different_words_or_wrong_scope_are_not_rescued_from_another_line(quote: str) -> None:
    result = engine().verify(artifact(), quote, {"line": 1})
    assert (result.verdict, result.content_support) == ("FAIL", "NOT_FOUND")


def test_missing_declared_scope_is_a_mismatch_even_if_text_exists_elsewhere() -> None:
    result = engine().verify(artifact(), "doctorate", {"line": 9})
    assert result.verdict == "FAIL"
    assert result.declared_locator == "MISMATCH"


@pytest.mark.parametrize("locator", [{}, {"section": "first", "human_verify": True}])
def test_content_found_with_unexecutable_locator_remains_unverified(
    locator: dict[str, object],
) -> None:
    result = engine().verify(artifact(), "doctorate", locator)
    assert result.content_support == "FOUND"
    assert result.verdict == "UNVERIFIED"
    assert result.binding == "UNBOUND"
    assert len(result.matches) == 1


def test_duplicate_source_locations_are_ambiguous_not_first_match_wins() -> None:
    result = engine().verify(artifact("doctorate doctorate"), "doctorate", {"line": 1})
    assert result.verdict == "UNVERIFIED"
    assert result.binding == "AMBIGUOUS"
    assert len(result.matches) == 2


@pytest.mark.parametrize("complete,reliable", [(False, True), (True, False), (False, False)])
@pytest.mark.parametrize("quote", ["doctorate", "missing"])
def test_incomplete_or_unreliable_reading_cannot_prove_a_negative_or_pass(
    complete: bool, reliable: bool, quote: str
) -> None:
    result = engine(SyntheticAdapter(complete=complete, reliable=reliable)).verify(
        artifact(), quote, {"line": 1}
    )
    assert result.verdict == "UNVERIFIED"
    assert result.content_support != "NOT_FOUND"
    if not reliable:
        assert result.content_support == "NOT_ESTABLISHED"


def test_unsupported_reader_and_missing_historical_version_stay_unverified() -> None:
    source = artifact()
    missing = ReaderIdentity(
        IDENTITY.name, "old", IDENTITY.parse_contract, IDENTITY.comparison_version
    )
    result = engine().verify(source, "doctorate", {"line": 1}, reader_identity=missing)
    assert result.reason_codes == ("READER_VERSION_UNAVAILABLE",)
    unknown = ArtifactInput(
        source.artifact_id, "application/unknown", source.source_url, source.sha256, source.content
    )
    assert engine().verify(unknown, "doctorate", {}).reason_codes == ("READER_UNSUPPORTED",)


def test_one_read_per_artifact_and_reader_version_without_cross_run_cache() -> None:
    reader = SyntheticAdapter()
    verifier = engine(reader)
    assert verifier.verify(artifact(), "doctorate", {"line": 1}).verdict == "PASS"
    assert verifier.verify(artifact(), "master", {"line": 2}).verdict == "PASS"
    assert reader.reads == 1
    assert engine(reader).verify(artifact(), "doctorate", {"line": 1}).verdict == "PASS"
    assert reader.reads == 2


def test_multiple_projections_of_one_original_location_are_counted_once() -> None:
    class ProjectedAdapter(SyntheticAdapter):
        def read(self, content: bytes) -> Representation:
            self.reads += 1
            return Representation(
                self.identity,
                sha256(content).hexdigest(),
                (
                    Projection(
                        "paragraph",
                        "doctorate",
                        (ProjectionRun(0, 9, (SourceSpan("text:1", 3, 12),)),),
                    ),
                    Projection(
                        "cell",
                        "xx doctorate",
                        (ProjectionRun(0, 12, (SourceSpan("text:1", 0, 12),)),),
                    ),
                ),
            )

        def resolve_scope(
            self, representation: Representation, locator: dict[str, object], *, source_url: str
        ) -> ScopeResolution:
            return ScopeResolution(
                "VERIFIED", tuple(p.projection_id for p in representation.projections), "SCOPE"
            )

    result = engine(ProjectedAdapter()).verify(artifact(), "doctorate", {"region": "same source"})
    assert result.verdict == "PASS"
    assert len(result.matches) == 1
    assert result.matches[0].source_spans == (SourceSpan("text:1", 3, 12),)


def test_normalized_offsets_are_not_reported_as_original_offsets() -> None:
    projection = Projection(
        "normalized",
        "Café",
        (
            ProjectionRun(0, 3, (SourceSpan("text:1", 8, 11),)),
            ProjectionRun(3, 4, (SourceSpan("text:1", 11, 13),)),
        ),
    )
    assert projection.source_spans(0, 4) == (SourceSpan("text:1", 8, 13),)


def test_projection_without_full_trace_is_rejected() -> None:
    with pytest.raises(ValueError, match="cover"):
        Projection("broken", "doctorate", (ProjectionRun(0, 3, (SourceSpan("text:1", 0, 3),)),))


def test_new_adapter_needs_no_change_to_the_verifier_or_delivery() -> None:
    class AlternateAdapter(SyntheticAdapter):
        identity = ReaderIdentity("another-local-reader", "1", "other/1", "literal/1")
        media_types = ("application/x-another-synthetic-format",)

    source = artifact()
    alternate = ArtifactInput(
        source.artifact_id,
        AlternateAdapter.media_types[0],
        source.source_url,
        source.sha256,
        source.content,
    )
    verifier = EvidenceVerifier(AdapterRegistry((SyntheticAdapter(), AlternateAdapter())))
    assert verifier.verify(alternate, "doctorate", {"line": 1}).verdict == "PASS"


def test_registry_does_not_silently_choose_between_active_readers() -> None:
    with pytest.raises(ValueError, match="active"):
        AdapterRegistry((SyntheticAdapter(), SyntheticAdapter()))


def test_failed_read_is_not_retried_for_each_quote_in_one_run() -> None:
    class BrokenReader(SyntheticAdapter):
        def read(self, content: bytes) -> Representation:
            self.reads += 1
            raise ExpectedParseError("SYNTHETIC_READ_FAILED")

    reader = BrokenReader()
    verifier = engine(reader)
    for quote in ("doctorate", "master"):
        result = verifier.verify(artifact(), quote, {"line": 1})
        assert result.verdict == "UNVERIFIED"
        assert result.reason_codes == ("READER_SYNTHETIC_READ_FAILED",)
    assert reader.reads == 1


def test_historical_reader_is_selected_exactly_and_not_substituted() -> None:
    class Historical(SyntheticAdapter):
        identity = ReaderIdentity("synthetic-text", "0", "synthetic-reader/0", "literal/0")

    active, historical = SyntheticAdapter(), Historical()
    verifier = EvidenceVerifier(AdapterRegistry((active,), historical=(historical,)))
    result = verifier.verify(
        artifact(), "doctorate", {"line": 1}, reader_identity=historical.identity
    )
    assert result.verdict == "PASS"
    assert (historical.reads, active.reads) == (1, 0)
    assert result.reader == historical.identity


def test_representation_cannot_claim_other_bytes() -> None:
    class WrongReader(SyntheticAdapter):
        def read(self, content: bytes) -> Representation:
            return replace(super().read(content), artifact_sha256="f" * 64)

    result = engine(WrongReader()).verify(artifact(), "doctorate", {"line": 1})
    assert result.verdict == "FAIL"
    assert result.reason_codes == ("REPRESENTATION_IDENTITY_MISMATCH",)


def test_ambiguity_is_visible_even_without_an_executable_locator() -> None:
    result = engine().verify(artifact("doctorate doctorate"), "doctorate", {})
    assert (result.content_support, result.declared_locator, result.binding, result.verdict) == (
        "FOUND",
        "UNBOUND",
        "AMBIGUOUS",
        "UNVERIFIED",
    )


def test_comparison_match_limit_is_incomplete_and_does_not_choose_first() -> None:
    result = engine().verify(artifact("doctorate " * 300), "doctorate", {"line": 1})
    assert result.verdict == "UNVERIFIED"
    assert result.binding == "AMBIGUOUS"
    assert result.reason_codes == ("MATCH_LIMIT_EXCEEDED",)


def test_only_partial_non_linear_trace_stays_unbound() -> None:
    class ContractingReader(SyntheticAdapter):
        def read(self, content: bytes) -> Representation:
            return Representation(
                self.identity,
                sha256(content).hexdigest(),
                (Projection("1", "abc", (ProjectionRun(0, 3, (SourceSpan("raw:1", 0, 4),)),)),),
            )

    result = engine(ContractingReader()).verify(artifact(), "b", {"line": 1})
    assert (result.verdict, result.content_support) == ("UNVERIFIED", "FOUND")
    assert result.reason_codes == ("PROJECTION_TRACE_INCOMPLETE",)


@pytest.mark.parametrize("complete,reliable", [(False, True), (True, False)])
def test_missing_scope_from_inadequate_reading_cannot_prove_locator_error(
    complete: bool, reliable: bool
) -> None:
    result = engine(SyntheticAdapter(complete=complete, reliable=reliable)).verify(
        artifact(), "doctorate", {"line": 9}
    )
    assert result.verdict == "UNVERIFIED"
    assert result.content_support == "NOT_ESTABLISHED"
    assert result.declared_locator == "UNBOUND"
