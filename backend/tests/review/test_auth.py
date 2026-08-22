from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.core.settings import Settings
from deepaha.review.auth import (
    REVIEWER_AUTHENTICATION_FAILURE,
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
    assert_reviewer_fixture_auth_enabled,
    parse_reviewer_bearer_token,
    require_reviewer_authority,
    reviewer_token_digest,
)

REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000000701")
NOW = datetime(2026, 8, 22, 11, 0, tzinfo=UTC)


def test_reviewer_credentials_are_digest_only_and_parser_rejects_ambiguous_values() -> None:
    token = "phase7-reviewer-token-0001"

    assert reviewer_token_digest(token) == (
        "b7112528784a074458a0cd718cd4657367e5c1796b87d111716efa544a9ab5eb"
    )
    assert parse_reviewer_bearer_token(f"Bearer {token}") == token
    assert parse_reviewer_bearer_token(f"bearer {token}") == token
    for invalid in (None, "", "Basic value", "Bearer", "Bearer value with-space"):
        with pytest.raises(ReviewerAuthenticationError, match=REVIEWER_AUTHENTICATION_FAILURE):
            parse_reviewer_bearer_token(invalid)


def test_reviewer_fixture_auth_is_fail_closed_outside_development_and_test() -> None:
    with pytest.raises(ReviewerAuthenticationError, match=REVIEWER_AUTHENTICATION_FAILURE):
        assert_reviewer_fixture_auth_enabled(Settings())
    with pytest.raises(ReviewerAuthenticationError, match=REVIEWER_AUTHENTICATION_FAILURE):
        assert_reviewer_fixture_auth_enabled(
            Settings(environment="production", reviewer_auth_mode="fixture")
        )

    assert_reviewer_fixture_auth_enabled(Settings(environment="test", reviewer_auth_mode="fixture"))


def test_reviewer_role_and_purpose_are_derived_and_checked_separately() -> None:
    principal = ReviewerPrincipal(
        reviewer_id=REVIEWER_ID,
        roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}),
        purposes=frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"}),
        synthetic=True,
    )

    require_reviewer_authority(principal, ReviewerRole.FEEDBACK_REVIEWER)
    with pytest.raises(ReviewerAuthenticationError, match=REVIEWER_AUTHENTICATION_FAILURE):
        require_reviewer_authority(principal, ReviewerRole.LABEL_CURATOR)
    with pytest.raises(ReviewerAuthenticationError, match=REVIEWER_AUTHENTICATION_FAILURE):
        require_reviewer_authority(
            ReviewerPrincipal(
                reviewer_id=REVIEWER_ID,
                roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}),
                purposes=frozenset(),
                synthetic=True,
            ),
            ReviewerRole.FEEDBACK_REVIEWER,
        )
