from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from deepaha.acquisition.contracts import (
    ChallengeType,
    ContentExpectations,
    FetchResult,
    ValidationStatus,
)
from deepaha.acquisition.validation import ContentValidator

FIXTURES = Path(__file__).parents[1] / "fixtures" / "acquisition" / "synthetic"
REQUEST_ID = UUID("019c0000-0000-7000-8000-000000000011")
SOURCE_ID = UUID("019c0000-0000-7000-8000-000000000012")
ENDPOINT_ID = UUID("019c0000-0000-7000-8000-000000000013")


def fetch_result(content: bytes, *, media_type: str = "text/html") -> FetchResult:
    return FetchResult.model_validate(
        {
            "request_id": REQUEST_ID,
            "source_id": SOURCE_ID,
            "endpoint_id": ENDPOINT_ID,
            "requested_url": "https://notices.example.gov/list/",
            "final_url": "https://notices.example.gov/list/",
            "redirect_chain": ["https://notices.example.gov/list/"],
            "strategy": "STATIC_HTTP",
            "fetched_at": datetime(2026, 8, 23, 10, 0, tzinfo=UTC),
            "outcome": "SUCCEEDED",
            "http_status": 200,
            "media_type": media_type,
            "safe_headers": {},
            "body": content,
            "body_object_key": None,
            "content_sha256": sha256(content).hexdigest(),
            "byte_size": len(content),
            "fetcher_name": "test-fetcher",
            "fetcher_version": "1.0.0",
            "error_code": None,
            "contract_version": "1.0.0",
        }
    )


def expectations(**changes: object) -> ContentExpectations:
    values: dict[str, object] = {
        "minimum_bytes": 20,
        "maximum_bytes": 1_000_000,
        "required_markers": [],
        "forbidden_markers": [],
        "required_selectors": ["main", "a.notice"],
        "minimum_discovered_count": 1,
        "structured_kind": None,
        "contract_version": "1.0.0",
    }
    values.update(changes)
    return ContentExpectations.model_validate(values)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_valid_html_passes_all_deterministic_checks() -> None:
    result = ContentValidator().evaluate(
        fetch_result(fixture("valid.html")),
        expectations(required_markers=["official notice"]),
        discovered_count=1,
    )

    assert result.status is ValidationStatus.VALID
    assert result.challenge_type is None
    assert result.discovered_count == 1
    assert result.diagnostic_codes == ()
    assert result.metrics == {
        "byte_size": len(fixture("valid.html")),
        "discovered_count": 1,
        "required_marker_matches": 1,
        "required_selector_matches": 2,
    }


def test_html_marker_validation_honors_a_declared_legacy_charset() -> None:
    content = (
        '<html><head><meta http-equiv="Content-Type" '
        'content="text/html; charset=gb2312"></head>'
        '<body><main><a class="notice">通知 公告</a></main></body></html>'
    ).encode("gb2312")

    result = ContentValidator().evaluate(
        fetch_result(content),
        expectations(required_markers=["通知"], minimum_discovered_count=0),
        discovered_count=0,
    )

    assert result.status is ValidationStatus.VALID
    assert result.metrics["required_marker_matches"] == 1


@pytest.mark.parametrize(
    ("fixture_name", "status", "challenge_type", "diagnostic"),
    [
        (
            "access-denied.html",
            ValidationStatus.ACCESS_DENIED,
            ChallengeType.ACCESS_CONTROL,
            "ACCESS_DENIED_MARKER",
        ),
        (
            "login.html",
            ValidationStatus.AUTH_REQUIRED,
            ChallengeType.AUTHENTICATION,
            "AUTH_REQUIRED_MARKER",
        ),
        (
            "captcha.html",
            ValidationStatus.CAPTCHA_REQUIRED,
            ChallengeType.CAPTCHA,
            "CAPTCHA_MARKER",
        ),
        (
            "javascript-challenge.html",
            ValidationStatus.CONTENT_CHALLENGE,
            ChallengeType.JAVASCRIPT_COOKIE,
            "JAVASCRIPT_COOKIE_CHALLENGE",
        ),
    ],
)
def test_generic_challenge_markers_fail_closed_before_structure_checks(
    fixture_name: str,
    status: ValidationStatus,
    challenge_type: ChallengeType,
    diagnostic: str,
) -> None:
    result = ContentValidator().evaluate(
        fetch_result(fixture(fixture_name)), expectations(), discovered_count=1
    )

    assert (result.status, result.challenge_type) == (status, challenge_type)
    assert result.diagnostic_codes == (diagnostic,)
    assert all("html" not in str(value).lower() for value in result.metrics.values())


@pytest.mark.parametrize("marker", [b"__tst_status", b"EO_Bot_Ssid"])
def test_generic_bot_cookie_challenge_markers_are_detected(marker: bytes) -> None:
    result = ContentValidator().evaluate(
        fetch_result(b"<script>" + marker + b"</script>"),
        expectations(minimum_bytes=1),
    )

    assert result.status is ValidationStatus.CONTENT_CHALLENGE
    assert result.challenge_type is ChallengeType.JAVASCRIPT_COOKIE
    assert result.diagnostic_codes == ("JAVASCRIPT_COOKIE_CHALLENGE",)


@pytest.mark.parametrize(
    ("content", "media_type", "changes", "status", "diagnostic"),
    [
        (b"", "text/html", {}, ValidationStatus.UNEXPECTED_CONTENT, "EMPTY_BODY"),
        (
            b"short",
            "text/html",
            {},
            ValidationStatus.UNEXPECTED_CONTENT,
            "BODY_TOO_SHORT",
        ),
        (
            fixture("valid.html"),
            "application/pdf",
            {},
            ValidationStatus.UNEXPECTED_CONTENT,
            "MIME_MISMATCH",
        ),
        (
            b'{"items":',
            "application/json",
            {
                "minimum_bytes": 1,
                "structured_kind": "JSON",
                "required_selectors": [],
                "minimum_discovered_count": 0,
            },
            ValidationStatus.UNEXPECTED_CONTENT,
            "MALFORMED_JSON",
        ),
        (
            b"<feed><item></feed>",
            "application/xml",
            {
                "minimum_bytes": 1,
                "structured_kind": "XML",
                "required_selectors": [],
                "minimum_discovered_count": 0,
            },
            ValidationStatus.UNEXPECTED_CONTENT,
            "MALFORMED_XML",
        ),
    ],
)
def test_invalid_bytes_mime_and_structured_content_are_visible(
    content: bytes,
    media_type: str,
    changes: dict[str, object],
    status: ValidationStatus,
    diagnostic: str,
) -> None:
    expected = expectations(**changes)
    result = ContentValidator().evaluate(fetch_result(content, media_type=media_type), expected)

    assert result.status is status
    assert result.diagnostic_codes == (diagnostic,)


def test_missing_marker_and_forbidden_marker_are_unexpected_content() -> None:
    missing = ContentValidator().evaluate(
        fetch_result(fixture("valid.html")),
        expectations(required_markers=["required but absent"]),
        discovered_count=1,
    )
    forbidden = ContentValidator().evaluate(
        fetch_result(fixture("valid.html")),
        expectations(forbidden_markers=["official notice"]),
        discovered_count=1,
    )

    assert missing.diagnostic_codes == ("REQUIRED_MARKER_MISSING",)
    assert forbidden.diagnostic_codes == ("FORBIDDEN_MARKER_PRESENT",)
    assert missing.status is forbidden.status is ValidationStatus.UNEXPECTED_CONTENT


def test_missing_selector_is_selector_drift() -> None:
    result = ContentValidator().evaluate(
        fetch_result(fixture("valid.html")),
        expectations(required_selectors=["main", "table.notices"]),
        discovered_count=1,
    )

    assert result.status is ValidationStatus.SELECTOR_DRIFT
    assert result.diagnostic_codes == ("REQUIRED_SELECTOR_MISSING",)
    assert result.metrics["required_selector_matches"] == 1


def test_zero_discovery_is_not_a_valid_empty_run() -> None:
    result = ContentValidator().evaluate(
        fetch_result(fixture("valid.html")), expectations(), discovered_count=0
    )

    assert result.status is ValidationStatus.ZERO_DISCOVERY_SUSPECT
    assert result.diagnostic_codes == ("MINIMUM_DISCOVERY_NOT_MET",)
    assert result.discovered_count == 0


def test_repeated_validation_is_byte_deterministic() -> None:
    validator = ContentValidator()
    source = fetch_result(fixture("valid.html"))
    expected = expectations(required_markers=["official notice"])

    first = validator.evaluate(source, expected, discovered_count=1)
    second = validator.evaluate(source, expected, discovered_count=1)

    assert first.model_dump_json() == second.model_dump_json()
