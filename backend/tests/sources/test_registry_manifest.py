import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError

from deepaha.sources.registry import SourceRegistryManifest, load_registry_manifest

FIXTURES = Path(__file__).parents[1] / "fixtures" / "sources"
VALID = FIXTURES / "registry-valid.json"
OFFICIAL = Path(__file__).parents[3] / "config" / "sources" / "phase2-official-endpoints.json"


def valid_payload() -> dict[str, object]:
    value: object = json.loads(VALID.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def endpoint(payload: dict[str, object]) -> dict[str, object]:
    sources = payload["sources"]
    assert isinstance(sources, list)
    entry = sources[0]
    assert isinstance(entry, dict)
    endpoints = entry["endpoints"]
    assert isinstance(endpoints, list)
    value = endpoints[0]
    assert isinstance(value, dict)
    return value


def write_payload(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_registry_manifest_accepts_strict_v02_manifest() -> None:
    manifest = load_registry_manifest(VALID)

    assert manifest.schema_version == "0.2.0"
    assert len(manifest.sources) == 1
    assert manifest.sources[0].endpoints[0].policy_version == "2026-08-21.1"


def test_load_registry_manifest_rejects_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + VALID.read_bytes())

    with pytest.raises(ValueError, match="UTF-8 BOM"):
        load_registry_manifest(path)


def test_load_registry_manifest_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "array.json"
    write_payload(path, [])

    with pytest.raises(ValueError, match="JSON object"):
        load_registry_manifest(path)


def test_manifest_rejects_unknown_fields() -> None:
    payload = valid_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="unexpected"):
        SourceRegistryManifest.model_validate(payload)


@pytest.mark.parametrize("duplicate", ["source_id", "public_id", "canonical_url"])
def test_manifest_rejects_duplicate_sources(duplicate: str) -> None:
    payload = valid_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    repeated = deepcopy(sources[0])
    assert isinstance(repeated, dict)
    source = repeated["source"]
    assert isinstance(source, dict)
    if duplicate != "source_id":
        source["source_id"] = "0198d239-4b00-7000-8000-000000000203"
    if duplicate != "public_id":
        source["public_id"] = "src_00000000000000000000000000000203"
    if duplicate != "canonical_url":
        source["canonical_url"] = "https://other.example.gov/"
    repeated_endpoints = repeated["endpoints"]
    assert isinstance(repeated_endpoints, list)
    repeated_endpoint = repeated_endpoints[0]
    assert isinstance(repeated_endpoint, dict)
    repeated_endpoint["endpoint_id"] = "0198d239-4b00-7000-8000-000000000204"
    repeated_endpoint["source_id"] = source["source_id"]
    repeated_endpoint["url"] = f"{source['canonical_url']}list/"
    repeated_endpoint["allowed_hosts"] = [
        "notices.example.gov" if duplicate == "canonical_url" else "other.example.gov"
    ]
    sources.append(repeated)

    with pytest.raises(ValidationError, match=f"duplicate {duplicate}"):
        SourceRegistryManifest.model_validate(payload)


def test_manifest_rejects_duplicate_endpoint_id() -> None:
    payload = valid_payload()
    endpoints = payload["sources"][0]["endpoints"]  # type: ignore[index]
    endpoints.append(deepcopy(endpoints[0]))

    with pytest.raises(ValidationError, match="duplicate endpoint_id"):
        SourceRegistryManifest.model_validate(payload)


@pytest.mark.parametrize("decision", ["UNKNOWN", "DISALLOWED"])
def test_active_endpoint_rejects_unapproved_robots_decision(decision: str) -> None:
    payload = valid_payload()
    endpoint(payload)["robots_decision"] = decision

    with pytest.raises(ValidationError, match="approved robots_decision"):
        SourceRegistryManifest.model_validate(payload)


def test_open_license_requires_name_and_url() -> None:
    payload = valid_payload()
    endpoint(payload)["content_use_basis"] = "OPEN_LICENSE"

    with pytest.raises(ValidationError, match="OPEN_LICENSE requires"):
        SourceRegistryManifest.model_validate(payload)


def test_link_only_endpoint_cannot_allow_fixture_storage() -> None:
    payload = valid_payload()
    endpoint(payload)["fixture_storage_allowed"] = True

    with pytest.raises(ValidationError, match="fixture storage requires OPEN_LICENSE"):
        SourceRegistryManifest.model_validate(payload)


def test_endpoint_url_must_be_inside_allowed_hosts() -> None:
    payload = valid_payload()
    endpoint(payload)["allowed_hosts"] = ["different.example.gov"]

    with pytest.raises(ValidationError, match="url host must be present"):
        SourceRegistryManifest.model_validate(payload)


def test_endpoint_url_must_not_embed_credentials() -> None:
    payload = valid_payload()
    endpoint(payload)["url"] = "https://operator:secret@notices.example.gov/list/"

    with pytest.raises(ValidationError, match="must not contain credentials"):
        SourceRegistryManifest.model_validate(payload)


def test_endpoint_source_id_must_match_owning_source() -> None:
    payload = valid_payload()
    endpoint(payload)["source_id"] = "0198d239-4b00-7000-8000-000000000299"

    with pytest.raises(ValidationError, match="endpoint source_id must match"):
        SourceRegistryManifest.model_validate(payload)


def test_loader_does_not_expand_environment_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = valid_payload()
    source = payload["sources"][0]["source"]  # type: ignore[index]
    source["canonical_url"] = "https://${REGISTRY_HOST}/"
    monkeypatch.setenv("REGISTRY_HOST", "notices.example.gov")
    path = tmp_path / "environment.json"
    write_payload(path, payload)

    manifest = load_registry_manifest(path)

    assert str(manifest.sources[0].source.canonical_url) != "https://notices.example.gov/"
    assert "registry_host" in str(manifest.sources[0].source.canonical_url).lower()


def test_invalid_fixture_is_rejected() -> None:
    with pytest.raises(ValidationError):
        load_registry_manifest(FIXTURES / "registry-invalid.json")


def test_official_registry_has_exactly_ten_bounded_link_only_candidates() -> None:
    manifest = load_registry_manifest(OFFICIAL)
    entries = manifest.sources

    assert len(entries) == 10
    assert {entry.source.authority_name for entry in entries} == {
        "中华人民共和国国家公务员局",
        "中华人民共和国人力资源和社会保障部",
        "国务院国有资产监督管理委员会",
        "中华人民共和国中央人民政府",
        "中华人民共和国教育部",
        "中国共产主义青年团中央委员会",
        "浙江省人力资源和社会保障厅",
        "浙江省人事考试院",
        "浙江省科学技术厅",
        "浙江省教育厅",
    }
    assert {
        (urlsplit(str(entry.endpoints[0].url)).hostname or "").removeprefix("www.")
        for entry in entries
    } == {
        "bm.scs.gov.cn",
        "mohrss.gov.cn",
        "sasac.gov.cn",
        "gov.cn",
        "moe.gov.cn",
        "gqt.org.cn",
        "rlsbt.zj.gov.cn",
        "zjks.com",
        "kjt.zj.gov.cn",
        "jyt.zj.gov.cn",
    }
    endpoints = [endpoint for entry in entries for endpoint in entry.endpoints]
    assert len(endpoints) == 10
    assert all(
        entry.source.active and endpoint.active for entry, endpoint in zip(entries, endpoints)
    )
    assert all(endpoint.minimum_interval_seconds == 21600 for endpoint in endpoints)
    assert all(endpoint.browser_policy == "NEVER" for endpoint in endpoints)
    assert all(endpoint.content_use_basis == "LINK_ONLY" for endpoint in endpoints)
    assert all(not endpoint.fixture_storage_allowed for endpoint in endpoints)
