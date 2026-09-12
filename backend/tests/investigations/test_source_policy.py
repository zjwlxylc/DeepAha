import json
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from deepaha.investigations import source_policy
from deepaha.investigations.source_policy import allowed_intake_source, sample_defaults
from deepaha.sources.models import Source, SourceEndpoint

SAMPLE_ENDPOINT_ID = "01a08e78-07a5-7596-9ca8-14b600b9784e"


def _endpoint(endpoint_id: str) -> SourceEndpoint:
    endpoint = Mock()
    endpoint.endpoint_id = endpoint_id
    return cast(SourceEndpoint, endpoint)


def _source(tier: str) -> Source:
    source = Mock()
    source.tier = tier
    return cast(Source, source)


def test_sample_defaults_reads_the_approved_row() -> None:
    row = sample_defaults(_endpoint(SAMPLE_ENDPOINT_ID))
    assert row["title"] == "浙江省省属事业单位2026年下半年集中公开招聘人员公告"


def test_sample_defaults_returns_empty_when_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_policy, "_samples_path", lambda: tmp_path / "missing.json")
    assert sample_defaults(_endpoint(SAMPLE_ENDPOINT_ID)) == {}


@pytest.mark.parametrize("payload", ["{not json", json.dumps({"endpoint_id": "x"})])
def test_sample_defaults_returns_empty_when_file_is_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    path = tmp_path / "direct-wma-samples.json"
    path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(source_policy, "_samples_path", lambda: path)
    assert sample_defaults(_endpoint(SAMPLE_ENDPOINT_ID)) == {}


def test_primary_source_is_allowed_without_reading_the_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unreadable() -> Path:
        raise AssertionError("PRIMARY intake must not read the aggregator allowlist")

    monkeypatch.setattr(source_policy, "_local_registry_path", _unreadable)
    assert allowed_intake_source(_source("OFFICIAL_PRIMARY"), _endpoint(SAMPLE_ENDPOINT_ID)) is True


def test_aggregator_is_denied_when_allowlist_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_policy, "_local_registry_path", lambda: tmp_path / "missing.json")
    source = _source("OFFICIAL_AGGREGATOR")
    assert allowed_intake_source(source, _endpoint(SAMPLE_ENDPOINT_ID)) is False


def test_untrusted_tier_is_never_allowed() -> None:
    assert (
        allowed_intake_source(_source("TRUSTED_SECONDARY"), _endpoint(SAMPLE_ENDPOINT_ID)) is False
    )
