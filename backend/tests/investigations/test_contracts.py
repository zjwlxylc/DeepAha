from uuid import uuid7

import pytest
from pydantic import ValidationError

from deepaha.investigations.contracts import CreateInvestigation, allowed_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/x",
        "https://official.example@127.0.0.1/x",
        "http://127.0.0.1/x",
        "https://official.example:8443/x",
        "https://official.example.evil.test/x",
        "https://official.example/x#fragment",
    ],
)
def test_notice_cannot_escape_approved_hosts(url: str) -> None:
    assert not allowed_url(url, ["official.example"])


def test_exact_public_host_and_default_https_port_are_allowed() -> None:
    assert allowed_url("https://official.example/notice?id=3", ["official.example"])


def test_registration_does_not_accept_live_authorization_or_private_extra() -> None:
    with pytest.raises(ValidationError):
        CreateInvestigation.model_validate(
            {
                "source_id": str(uuid7()),
                "endpoint_id": str(uuid7()),
                "notice_url": "https://official.example/n",
                "brief": "公开公告调查",
                "live_authorized": True,
            }
        )


def test_invalid_wall_time_does_not_silently_expand_budget() -> None:
    with pytest.raises(ValidationError):
        CreateInvestigation(
            source_id=uuid7(),
            endpoint_id=uuid7(),
            notice_url="https://official.example/n",
            brief="公开资料",
            wall_time_seconds=3601,
        )
