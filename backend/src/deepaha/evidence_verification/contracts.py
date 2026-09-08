import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Literal, Protocol

type Verdict = Literal["PASS", "FAIL", "UNVERIFIED"]
type ContentSupport = Literal["FOUND", "NOT_FOUND", "NOT_ESTABLISHED"]
type LocatorStatus = Literal["VERIFIED", "UNBOUND", "UNSUPPORTED", "INVALID", "MISMATCH"]
type BindingStatus = Literal["BOUND", "UNBOUND", "AMBIGUOUS"]
type Precision = Literal["ARTIFACT", "SCOPE", "SPAN", "NONE"]

VERIFIER_VERSION = "evidence-literal/1"


@dataclass(frozen=True, slots=True)
class ReaderIdentity:
    name: str
    version: str
    parse_contract: str
    comparison_version: str


@dataclass(frozen=True, slots=True)
class ArtifactInput:
    artifact_id: str
    media_type: str
    source_url: str
    sha256: str
    content: bytes


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Character range in a Reader-defined original text node, never file bytes.

    The pinned Reader replays origin_id. Overlapping projections must use the
    same origin identity so the verifier can distinguish locations from views.
    """

    origin_id: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if not self.origin_id or type(self.start) is not int or type(self.end) is not int:
            raise ValueError("source span needs an identity and integer offsets")
        if not 0 <= self.start < self.end:
            raise ValueError("source span must be ordered and nonempty")


@dataclass(frozen=True, slots=True)
class ProjectionRun:
    start: int
    end: int
    sources: tuple[SourceSpan, ...]


@dataclass(frozen=True, slots=True)
class Projection:
    projection_id: str
    text: str
    runs: tuple[ProjectionRun, ...]

    def __post_init__(self) -> None:
        cursor = 0
        for run in self.runs:
            if run.start != cursor or run.end <= run.start or run.end > len(self.text):
                raise ValueError("projection trace must cover its text without gaps or overlap")
            cursor = run.end
        if not self.projection_id or not self.text or cursor != len(self.text):
            raise ValueError("projection trace must cover nonempty text")

    @property
    def sha256(self) -> str:
        return sha256(self.text.encode()).hexdigest()

    def source_spans(self, start: int, end: int) -> tuple[SourceSpan, ...] | None:
        if not 0 <= start < end <= len(self.text):
            raise ValueError("match offsets are outside the projection")
        spans: list[SourceSpan] = []
        for run in self.runs:
            lo, hi = max(start, run.start), min(end, run.end)
            if lo >= hi or not run.sources:
                continue
            source = run.sources[0]
            if len(run.sources) == 1 and run.end - run.start == source.end - source.start:
                span = SourceSpan(
                    source.origin_id, source.start + lo - run.start, source.start + hi - run.start
                )
                selected: tuple[SourceSpan, ...] = (span,)
            elif lo == run.start and hi == run.end:
                # A normalization cluster can contract/expand. Only its full
                # mapped range is known; do not invent partial source offsets.
                selected = run.sources
            else:
                return None
            for span in selected:
                if spans and spans[-1].origin_id == span.origin_id and spans[-1].end == span.start:
                    spans[-1] = SourceSpan(span.origin_id, spans[-1].start, span.end)
                else:
                    spans.append(span)
        return tuple(spans) or None


@dataclass(frozen=True, slots=True)
class Representation:
    reader: ReaderIdentity
    artifact_sha256: str
    projections: tuple[Projection, ...]
    complete: bool = True
    reliable: bool = True
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = [p.projection_id for p in self.projections]
        if len(ids) != len(set(ids)):
            raise ValueError("projection identities must be unique")

    @property
    def sha256(self) -> str:
        return sha256(
            json.dumps(
                {
                    "reader": asdict(self.reader),
                    "artifact_sha256": self.artifact_sha256,
                    "projections": [asdict(p) for p in self.projections],
                    "complete": self.complete,
                    "reliable": self.reliable,
                    "reason_codes": self.reason_codes,
                },
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class ScopeResolution:
    status: LocatorStatus
    projection_ids: tuple[str, ...]
    precision: Precision
    complete: bool = True
    requires_human_review: bool = False
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceMatch:
    projection_id: str
    projection_sha256: str
    projection_start: int
    projection_end: int
    source_spans: tuple[SourceSpan, ...]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    artifact_id: str
    artifact_sha256: str
    quote: str
    original_locator: dict[str, object]
    reader: ReaderIdentity | None
    representation_sha256: str | None
    content_support: ContentSupport
    declared_locator: LocatorStatus
    binding: BindingStatus
    precision: Precision
    verdict: Verdict
    matches: tuple[EvidenceMatch, ...]
    reason_codes: tuple[str, ...]
    verifier_version: str = VERIFIER_VERSION


class EvidenceAdapter(Protocol):
    @property
    def identity(self) -> ReaderIdentity: ...

    @property
    def media_types(self) -> tuple[str, ...]: ...

    def read(self, content: bytes) -> Representation: ...

    def normalize_quote(self, quote: str) -> str: ...

    def resolve_scope(
        self, representation: Representation, locator: dict[str, object], *, source_url: str
    ) -> ScopeResolution: ...
