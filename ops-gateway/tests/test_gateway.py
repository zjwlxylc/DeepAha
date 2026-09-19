"""Original gateway contracts updated for explicit environment/body idempotency."""

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from test_closeout import READ, TOKEN, configured, headers, payload

from deepaha_ops.audit import redact_text
from deepaha_ops.main import create_app


def app_client(tmp_path, monkeypatch, enabled=True):
    settings = configured(tmp_path)
    settings.mutations_enabled = enabled
    app = create_app(settings)

    async def fake(args):
        return 0, "action:" + " ".join(args)

    monkeypatch.setattr(app.state.runner, "_run", fake)
    return TestClient(app)


def test_health_auth_and_host(tmp_path, monkeypatch):
    with app_client(tmp_path, monkeypatch) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/v1/status?environment=staging").status_code == 401
        assert (
            c.get("/v1/status?environment=staging", headers=headers("bad-token")).status_code == 401
        )
        assert c.get("/health", headers={"Host": "evil.invalid"}).status_code == 400
        assert c.get("/v1/status?environment=staging", headers=headers()).status_code == 200


def test_read_token_cannot_deploy(tmp_path, monkeypatch):
    with app_client(tmp_path, monkeypatch) as c:
        body = payload(commit_sha="a" * 40)
        body.pop("target")
        assert c.post("/v1/deploy", headers=headers(READ), json=body).status_code == 403


def test_invalid_parameters_and_disabled_optional_actions(tmp_path, monkeypatch):
    with app_client(tmp_path, monkeypatch) as c:
        for target in ["web", "sshd", "api;id", "/etc/passwd"]:
            assert (
                c.post("/v1/restart", headers=headers(), json=payload(target=target)).status_code
                == 422
            )
        for key, value in [
            ("expected_current", "main"),
            ("idempotency_key", "short"),
            ("path", "/tmp"),
        ]:
            assert (
                c.post("/v1/restart", headers=headers(), json=payload(**{key: value})).status_code
                == 422
            )
        assert c.post("/v1/beta-users", headers=headers(), json={}).status_code == 404


def test_mutations_disabled_fail_closed(tmp_path, monkeypatch):
    with app_client(tmp_path, monkeypatch, False) as c:
        assert c.post("/v1/restart", json=payload(), headers=headers()).status_code == 503


def test_logs_allowlisted_bounded(tmp_path, monkeypatch):
    with app_client(tmp_path, monkeypatch) as c:
        assert (
            c.get(
                "/v1/logs?environment=staging&service=api&lines=20", headers=headers()
            ).status_code
            == 200
        )
        for query in ["service=sshd&lines=20", "service=api&lines=501", "service=api&lines=1"]:
            assert (
                c.get("/v1/logs?environment=staging&" + query, headers=headers()).status_code == 422
            )
        assert c.get("/v1/gateway/logs", headers=headers()).status_code == 403


def test_operation_completes_and_persists(tmp_path, monkeypatch):
    with app_client(tmp_path, monkeypatch) as c:
        op = c.post("/v1/restart", json=payload(), headers=headers()).json()
        for _ in range(50):
            result = c.get("/v1/operations/" + op["id"], headers=headers()).json()
            if result["status"] == "SUCCEEDED":
                break
            time.sleep(0.01)
        assert result["status"] == "SUCCEEDED"
        assert "restart staging" in result["output"]
    assert TOKEN not in (tmp_path / "audit.jsonl").read_text()


def test_production_requires_non_model_authorization(tmp_path, monkeypatch):
    settings = configured(tmp_path)
    scopes = json.loads(settings.token_hashes_json)
    scopes[hashlib.sha256(TOKEN.encode()).hexdigest()] += ["production:deploy"]
    settings.token_hashes_json = json.dumps(scopes)
    with TestClient(create_app(settings)) as c:
        body = payload(environment="production", commit_sha="b" * 40)
        body.pop("target")
        response = c.post("/v1/deploy", json=body, headers=headers())
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "PER_OPERATION_HUMAN_AUTH_REQUIRED"
        body["confirmation"] = "DEPLOY_PRODUCTION"
        assert c.post("/v1/deploy", json=body, headers=headers()).status_code == 422


def test_audit_redaction():
    secret = "synthetic-secret-value"
    assert secret not in redact_text(
        f"Authorization: Bearer {secret} password={secret} token={secret}"
    )


def test_streaming_output_is_bounded(tmp_path):
    app = create_app(configured(tmp_path))
    runner = app.state.runner
    runner.settings.adapter_path = Path(sys.executable)
    runner.settings.adapter_use_sudo = False
    code, out = asyncio.run(runner._run(["-c", 'import sys; sys.stdout.write("x"*4000000)']))
    assert code == 0
    assert len(out) <= runner.settings.max_output_bytes + 40
    assert out.endswith("[OUTPUT_TRUNCATED]")
