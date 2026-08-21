from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.sources.health import SourceHealthSummary


def test_source_health_summary_is_an_immutable_derived_value() -> None:
    summary = SourceHealthSummary(
        endpoint_id=UUID("0198d239-4b00-7000-8000-000000000401"),
        source_id=UUID("0198d239-4b00-7000-8000-000000000402"),
        as_of=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        last_attempt_at=None,
        last_success_at=None,
        consecutive_failures=0,
        attempts_24h=0,
        successes_24h=0,
        not_modified_24h=0,
        failures_24h=0,
        latest_artifact_id=None,
        latest_content_sha256=None,
        parse_successes=0,
        parse_needs_review=0,
        parse_failures=0,
    )

    with pytest.raises(FrozenInstanceError):
        summary.attempts_24h = 1  # type: ignore[misc]
