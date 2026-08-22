import pytest

from deepaha.core.settings import Settings
from deepaha.personal.auth import (
    AuthenticationError,
    assert_fixture_auth_enabled,
    parse_bearer_token,
    token_digest,
)


def test_token_digest_is_stable_and_bearer_parser_rejects_ambiguous_credentials() -> None:
    token = "0123456789abcdef"

    assert token_digest(token) == "9f9f5111f7b27a781f1f1ddde5ebc2dd2b796bfc7365c9c28b548e564176929f"
    assert parse_bearer_token(f"Bearer {token}") == token
    assert parse_bearer_token(f"bearer {token}") == token

    for invalid in (None, "", "Basic value", "Bearer", "Bearer value with-space"):
        with pytest.raises(AuthenticationError, match="personal authentication failed"):
            parse_bearer_token(invalid)


def test_fixture_auth_is_disabled_by_default_and_never_allowed_in_production() -> None:
    with pytest.raises(AuthenticationError, match="personal authentication failed"):
        assert_fixture_auth_enabled(Settings())
    with pytest.raises(AuthenticationError, match="personal authentication failed"):
        assert_fixture_auth_enabled(
            Settings(environment="production", personal_auth_mode="fixture")
        )

    assert_fixture_auth_enabled(Settings(environment="test", personal_auth_mode="fixture"))
