from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

from deepaha.documents.parser import ExpectedParseError
from deepaha.evidence_verification.contracts import (
    ArtifactInput,
    EvidenceMatch,
    Projection,
    ReaderIdentity,
    Representation,
    SourceSpan,
    VerificationResult,
)
from deepaha.evidence_verification.registry import AdapterRegistry

MAX_MATCHES = 256


class RepresentationIdentityError(ValueError):
    pass


class EvidenceVerifier:
    """One delivery/replay's cache and literal checks; no fact or approval inputs."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry
        self._representations: dict[tuple[str, str, ReaderIdentity], Representation] = {}
        self._indexes: dict[tuple[str, str, ReaderIdentity], dict[str, Projection]] = {}
        self._hashes: dict[tuple[str, str, ReaderIdentity], str] = {}
        self._read_errors: dict[tuple[str, str, ReaderIdentity], str] = {}

    def read(self, artifact: ArtifactInput, identity: ReaderIdentity) -> Representation:
        """Read through the same pinned, validated cache used by literal checks."""
        if sha256(artifact.content).hexdigest() != artifact.sha256:
            raise RepresentationIdentityError("ARTIFACT_HASH_MISMATCH")
        adapter = self._registry.select(artifact.media_type, identity)
        if adapter is None:
            raise LookupError("READER_VERSION_UNAVAILABLE")
        key = artifact.artifact_id, artifact.sha256, identity
        representation = self._representations.get(key)
        if representation is None:
            representation = adapter.read(artifact.content)
            if (
                representation.artifact_sha256 != artifact.sha256
                or representation.reader != identity
            ):
                raise RepresentationIdentityError("REPRESENTATION_IDENTITY_MISMATCH")
            self._representations[key] = representation
            self._indexes[key] = {p.projection_id: p for p in representation.projections}
            self._hashes[key] = representation.sha256
        return representation

    def verify(
        self,
        artifact: ArtifactInput,
        quote: str,
        locator: dict[str, object],
        *,
        reader_identity: ReaderIdentity | None = None,
    ) -> VerificationResult:
        digest = sha256(artifact.content).hexdigest()
        result = VerificationResult(
            artifact.artifact_id,
            digest,
            quote,
            deepcopy(locator),
            None,
            None,
            "NOT_ESTABLISHED",
            "UNBOUND",
            "UNBOUND",
            "NONE",
            "UNVERIFIED",
            (),
            (),
        )
        if digest != artifact.sha256:
            return replace(result, verdict="FAIL", reason_codes=("ARTIFACT_HASH_MISMATCH",))
        adapter = self._registry.select(artifact.media_type, reader_identity)
        if adapter is None:
            code = "READER_VERSION_UNAVAILABLE" if reader_identity else "READER_UNSUPPORTED"
            return replace(result, reason_codes=(code,))
        result = replace(result, reader=adapter.identity)
        key = artifact.artifact_id, digest, adapter.identity
        if key in self._read_errors:
            return replace(result, reason_codes=(self._read_errors[key],))
        representation = self._representations.get(key)
        try:
            if representation is None:
                representation = self.read(artifact, adapter.identity)
            scope = adapter.resolve_scope(
                representation, deepcopy(locator), source_url=artifact.source_url
            )
            comparable_quote = adapter.normalize_quote(quote)
        except RepresentationIdentityError:
            return replace(
                result, verdict="FAIL", reason_codes=("REPRESENTATION_IDENTITY_MISMATCH",)
            )
        except ExpectedParseError as error:
            code = f"READER_{error.code}"
            if representation is None:
                self._read_errors[key] = code
            return replace(result, reason_codes=(code,))
        result = replace(
            result,
            representation_sha256=self._hashes[key],
            declared_locator=scope.status,
            precision=scope.precision,
        )
        if not comparable_quote.strip():
            return replace(result, verdict="FAIL", reason_codes=("EVIDENCE_QUOTE_EMPTY",))
        if scope.status == "MISMATCH" and (
            not representation.reliable or not representation.complete or not scope.complete
        ):
            reason = "READING_UNRELIABLE" if not representation.reliable else "READING_INCOMPLETE"
            return replace(
                result,
                declared_locator="UNBOUND",
                reason_codes=(*representation.reason_codes, *scope.reason_codes, reason),
            )
        if scope.status in {"INVALID", "MISMATCH"}:
            return replace(
                result, verdict="FAIL", reason_codes=(f"EVIDENCE_LOCATOR_{scope.status}",)
            )
        by_id = self._indexes[key]
        if any(identity not in by_id for identity in scope.projection_ids):
            return replace(result, reason_codes=("READER_SCOPE_INVALID",))
        matches: dict[tuple[SourceSpan, ...], EvidenceMatch] = {}
        found = False
        trace_complete = True
        for identity in scope.projection_ids:
            projection = by_id[identity]
            cursor = 0
            while (start := projection.text.find(comparable_quote, cursor)) >= 0:
                found = True
                end = start + len(comparable_quote)
                spans = projection.source_spans(start, end)
                if spans is None:
                    trace_complete = False
                elif spans not in matches:
                    matches[spans] = EvidenceMatch(identity, projection.sha256, start, end, spans)
                    if len(matches) > MAX_MATCHES:
                        return replace(
                            result,
                            content_support="FOUND"
                            if representation.reliable
                            else "NOT_ESTABLISHED",
                            binding="AMBIGUOUS",
                            matches=tuple(matches.values())[:MAX_MATCHES],
                            reason_codes=("MATCH_LIMIT_EXCEEDED",),
                        )
                cursor = start + 1
        result = replace(result, matches=tuple(matches.values()))
        if len(matches) > 1:
            result = replace(result, binding="AMBIGUOUS")
        if representation.reliable and found:
            result = replace(result, content_support="FOUND")
        reasons = (*representation.reason_codes, *scope.reason_codes)
        if not representation.reliable:
            return replace(result, reason_codes=(*reasons, "READING_UNRELIABLE"))
        if not representation.complete or not scope.complete:
            return replace(result, reason_codes=(*reasons, "READING_INCOMPLETE"))
        if (
            scope.status != "VERIFIED"
            or scope.requires_human_review
            or locator.get("human_verify") is True
        ):
            return replace(result, reason_codes=(*reasons, "DECLARED_LOCATOR_UNVERIFIED"))
        if not found:
            return replace(
                result,
                content_support="NOT_FOUND",
                verdict="FAIL",
                reason_codes=(*reasons, "EVIDENCE_QUOTE_MISMATCH"),
            )
        if not trace_complete:
            return replace(result, reason_codes=(*reasons, "PROJECTION_TRACE_INCOMPLETE"))
        if len(matches) != 1:
            return replace(
                result, binding="AMBIGUOUS", reason_codes=(*reasons, "EVIDENCE_LOCATION_AMBIGUOUS")
            )
        return replace(result, verdict="PASS", binding="BOUND", reason_codes=reasons)
