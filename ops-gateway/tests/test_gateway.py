from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from deepaha_ops.audit import redact_text
from deepaha_ops.config import Settings
from deepaha_ops.main import create_app

TOKEN = "test-token-with-more-than-thirty-two-characters"
READ_TOKEN = "read-only-token-with-more-than-thirty-two-chars"


def token_map() -> str:
    return json.dumps(
        {
            hashlib.sha256(TOKEN.encode()).hexdigest(): [
                "read",
                "deploy",
                "backup",
                "rollback",
                "restart",
                "user_admin",
            ],
            hashlib.sha256(READ_TOKEN.encode()).hexdigest(): ["read"],
        }
    )


def make_adapter(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        ' status) echo \'{"release":"abc"}\' ;;\n'
        ' logs) echo "log $2 $3" ;;\n'
        ' *) echo "action:$*" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def settings(
    tmp_path: Path,
    *,
    mutations: bool = True,
) -> Settings:
    adapter = tmp_path / "adapter.sh"
    make_adapter(adapter)
    return Settings(
        environment="test",
        trusted_hosts=["testserver"],
        mutations_enabled=mutations,
        adapter_path=adapter,
        adapter_use_sudo=False,
        state_dir=tmp_path / "state",
        audit_log=tmp_path / "audit" / "audit.jsonl",
        token_hashes_json=token_map(),
        command_timeout_seconds=10,
    )


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_is_public(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_status_requires_auth(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/v1/status").status_code == 401
        response = client.get("/v1/status", headers=auth())
    assert response.status_code == 200
    assert "abc" in response.json()["adapter_status"]


def test_read_only_token_cannot_deploy(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/v1/deploy",
            headers={
                **auth(READ_TOKEN),
                "Idempotency-Key": "deploy-readonly-1",
            },
            json={
                "environment": "staging",
                "commit_sha": "a" * 40,
            },
        )
    assert response.status_code == 403


def test_production_deploy_requires_confirmation_and_full_sha(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        bad_sha = client.post(
            "/v1/deploy",
            headers={
                **auth(),
                "Idempotency-Key": "deploy-production-1",
            },
            json={
                "environment": "production",
                "commit_sha": "main",
                "confirmation": "DEPLOY_PRODUCTION",
            },
        )
        missing_confirm = client.post(
            "/v1/deploy",
            headers={
                **auth(),
                "Idempotency-Key": "deploy-production-2",
            },
            json={
                "environment": "production",
                "commit_sha": "b" * 40,
            },
        )
    assert bad_sha.status_code == 422
    assert missing_confirm.status_code == 400


def test_idempotency_returns_same_operation(
    tmp_path: Path,
) -> None:
    headers = {
        **auth(),
        "Idempotency-Key": "deploy-staging-same-1",
    }
    with TestClient(create_app(settings(tmp_path))) as client:
        first = client.post(
            "/v1/deploy",
            headers=headers,
            json={
                "environment": "staging",
                "commit_sha": "c" * 40,
            },
        )
        second = client.post(
            "/v1/deploy",
            headers=headers,
            json={
                "environment": "staging",
                "commit_sha": "c" * 40,
            },
        )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["idempotent_replay"] is True


def test_mutations_disabled_fail_closed(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings(tmp_path, mutations=False))) as client:
        response = client.post(
            "/v1/restart",
            headers={
                **auth(),
                "Idempotency-Key": "restart-disabled-1",
            },
            json={"target": "web"},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MUTATIONS_DISABLED"


def test_logs_are_allowlisted_and_bounded(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        okay = client.get(
            "/v1/logs?service=api&lines=20",
            headers=auth(),
        )
        bad = client.get(
            "/v1/logs?service=sshd&lines=20",
            headers=auth(),
        )
        too_many = client.get(
            "/v1/logs?service=api&lines=9999",
            headers=auth(),
        )
    assert okay.status_code == 200
    assert bad.status_code == 422
    assert too_many.status_code == 422


def test_operation_completes_and_persists_output(
    tmp_path: Path,
) -> None:
    headers = {
        **auth(),
        "Idempotency-Key": "restart-web-complete-1",
    }
    with TestClient(create_app(settings(tmp_path))) as client:
        queued = client.post(
            "/v1/restart",
            headers=headers,
            json={"target": "web"},
        )
        operation_id = queued.json()["id"]
        deadline = time.time() + 2
        final = None
        while time.time() < deadline:
            final = client.get(
                f"/v1/operations/{operation_id}",
                headers=auth(),
            ).json()
            if final["status"] in {"SUCCEEDED", "FAILED"}:
                break
            time.sleep(0.02)
    assert final is not None
    assert final["status"] == "SUCCEEDED"
    assert "action:restart web" in final["output"]


def test_audit_does_not_record_bearer_token(
    tmp_path: Path,
) -> None:
    secret = "super-secret-token-value"
    text = f"Authorization: Bearer {secret} token={secret} password={secret}"
    redacted = redact_text(text)
    assert secret not in redacted
    assert redacted.count("[REDACTED]") == 3
