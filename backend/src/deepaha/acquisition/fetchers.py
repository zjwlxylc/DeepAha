from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import FetchRequest, FetchResult, FetchStrategy
from deepaha.artifacts.models import RawArtifact
from deepaha.sources.collector import CollectionRunner
from deepaha.sources.models import SourceEndpoint


class FetchPolicyMismatch(RuntimeError):
    def __init__(self) -> None:
        self.code = "FETCH_POLICY_MISMATCH"
        super().__init__(self.code)


class StaticHttpFetcher:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        collection_runner: CollectionRunner,
        fetcher_name: str = "deepaha-static-http",
        fetcher_version: str = "1.0.0",
    ) -> None:
        self._session_factory = session_factory
        self._collection_runner = collection_runner
        self._fetcher_name = fetcher_name
        self._fetcher_version = fetcher_version

    def fetch(self, request: FetchRequest) -> FetchResult:
        self._require_endpoint_policy(request)
        run = self._collection_runner.collect(
            request.endpoint_id,
            requested_url=str(request.requested_url),
            max_attempts=request.max_attempts,
            timeout_seconds=request.timeout_seconds,
            max_bytes=request.max_bytes,
            capture_unexpected_content=True,
        )
        if not run.attempts:
            raise RuntimeError("CollectionRunner returned no attempt")
        attempt = run.attempts[-1]
        artifact = self._load_artifact(attempt.artifact_id)
        safe_headers: dict[str, str] = {}
        if attempt.response_etag is not None:
            safe_headers["etag"] = attempt.response_etag
        if attempt.response_last_modified is not None:
            safe_headers["last-modified"] = attempt.response_last_modified

        return FetchResult.model_validate(
            {
                "request_id": request.request_id,
                "source_id": request.source_id,
                "endpoint_id": request.endpoint_id,
                "observation_id": attempt.observation_id,
                "artifact_id": attempt.artifact_id,
                "requested_url": attempt.requested_url,
                "final_url": attempt.resolved_url,
                "redirect_chain": attempt.redirect_chain,
                "strategy": request.strategy,
                "fetched_at": attempt.completed_at,
                "outcome": attempt.outcome,
                "http_status": attempt.http_status,
                "media_type": (
                    attempt.media_type
                    if attempt.media_type is not None
                    else artifact.media_type
                    if artifact is not None
                    else None
                ),
                "safe_headers": safe_headers,
                "body": None,
                "body_object_key": artifact.object_key if artifact is not None else None,
                "content_sha256": artifact.content_sha256 if artifact is not None else None,
                "byte_size": artifact.byte_size if artifact is not None else None,
                "fetcher_name": self._fetcher_name,
                "fetcher_version": self._fetcher_version,
                "error_code": attempt.error_code,
                "contract_version": "1.0.0",
            }
        )

    def _require_endpoint_policy(self, request: FetchRequest) -> None:
        with self._session_factory() as session:
            endpoint = session.get(SourceEndpoint, request.endpoint_id)
            if endpoint is None:
                raise LookupError(f"SourceEndpoint not found: {request.endpoint_id}")
            consistent = (
                request.strategy is FetchStrategy.STATIC_HTTP
                and request.source_id == endpoint.source_id
                and request.allowed_hosts == tuple(endpoint.allowed_hosts)
                and request.expected_media_types == tuple(endpoint.expected_media_types)
                and request.policy_version == endpoint.policy_version
                and request.timeout_seconds <= endpoint.timeout_seconds
                and request.max_attempts <= endpoint.max_attempts
            )
            if not consistent:
                raise FetchPolicyMismatch

    def _load_artifact(self, artifact_id: UUID | None) -> RawArtifact | None:
        if artifact_id is None:
            return None
        with self._session_factory() as session:
            artifact = session.get(RawArtifact, artifact_id)
            if artifact is None:
                raise RuntimeError("Collection attempt references a missing RawArtifact")
            return artifact


__all__ = ["FetchPolicyMismatch", "StaticHttpFetcher"]
