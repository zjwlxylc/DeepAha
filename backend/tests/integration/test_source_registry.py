from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deepaha.sources.models import Source, SourceEndpoint
from deepaha.sources.registry import (
    SourcePolicyConflict,
    SourceRegistryManifest,
    import_registry,
    load_registry_manifest,
)

pytestmark = pytest.mark.integration
MANIFEST_PATH = Path(__file__).parents[1] / "fixtures" / "sources" / "registry-valid.json"


@pytest.fixture
def manifest() -> SourceRegistryManifest:
    return load_registry_manifest(MANIFEST_PATH)


def change_timeout(manifest: SourceRegistryManifest, timeout: int) -> SourceRegistryManifest:
    payload = deepcopy(manifest.model_dump(mode="json"))
    payload["sources"][0]["endpoints"][0]["timeout_seconds"] = timeout
    return SourceRegistryManifest.model_validate(payload)


def test_registry_import_is_idempotent(session: Session, manifest: SourceRegistryManifest) -> None:
    first = import_registry(session, manifest)
    second = import_registry(session, manifest)

    assert first.created_sources == 1
    assert first.created_endpoints == 1
    assert second.created_sources == 0
    assert second.created_endpoints == 0
    assert session.scalar(select(func.count()).select_from(Source)) == 1
    assert session.scalar(select(func.count()).select_from(SourceEndpoint)) == 1


def test_changed_meaning_under_same_policy_version_fails(
    session: Session, manifest: SourceRegistryManifest
) -> None:
    import_registry(session, manifest)

    with pytest.raises(SourcePolicyConflict, match="SOURCE_POLICY_CONFLICT"):
        import_registry(session, change_timeout(manifest, 61))


def test_changed_source_meaning_fails(session: Session, manifest: SourceRegistryManifest) -> None:
    import_registry(session, manifest)
    payload = deepcopy(manifest.model_dump(mode="json"))
    payload["sources"][0]["source"]["authority_name"] = "Changed authority"
    changed = SourceRegistryManifest.model_validate(payload)

    with pytest.raises(SourcePolicyConflict, match="SOURCE_POLICY_CONFLICT"):
        import_registry(session, changed)


def test_new_policy_version_preserves_old_endpoint(
    session: Session, manifest: SourceRegistryManifest
) -> None:
    import_registry(session, manifest)
    payload = deepcopy(manifest.model_dump(mode="json"))
    endpoint = payload["sources"][0]["endpoints"][0]
    endpoint["endpoint_id"] = "0198d239-4b00-7000-8000-000000000205"
    endpoint["policy_version"] = "2026-08-21.2"
    endpoint["timeout_seconds"] = 61
    changed = SourceRegistryManifest.model_validate(payload)

    result = import_registry(session, changed)

    assert result.created_sources == 0
    assert result.created_endpoints == 1
    assert session.scalar(select(func.count()).select_from(SourceEndpoint)) == 2
