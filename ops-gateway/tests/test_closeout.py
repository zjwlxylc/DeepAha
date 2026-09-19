import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from deepaha_ops.audit import AuditEvent, AuditLog
from deepaha_ops.config import Settings
from deepaha_ops.main import create_app

TOKEN = "synthetic-staging-token-with-adequate-test-length"
READ = "synthetic-readonly-token-with-adequate-test-length"


def configured(tmp_path):
    return Settings(
        state_dir=tmp_path / "state",
        audit_log=tmp_path / "audit.jsonl",
        trusted_hosts=["testserver"],
        mutations_enabled=True,
        staging_mutations_enabled=True,
        token_hashes_json=json.dumps(
            {
                hashlib.sha256(TOKEN.encode()).hexdigest(): [
                    "staging:read",
                    "staging:restart",
                    "staging:deploy",
                    "staging:backup",
                    "staging:rollback",
                ],
                hashlib.sha256(READ.encode()).hexdigest(): ["staging:read"],
            }
        ),
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app(configured(tmp_path))
    calls = []

    async def run(args):
        calls.append(args)
        return 0, json.dumps({"environment": "staging", "current_sha": "a" * 40})

    monkeypatch.setattr(app.state.runner, "_run", run)
    with TestClient(app) as client:
        yield client, calls, app


def headers(token=TOKEN):
    return {"Authorization": "Bearer " + token}


def payload(**kw):
    return {
        "environment": "staging",
        "target": "api",
        "expected_current": "a" * 40,
        "idempotency_key": "test-request-0001",
        **kw,
    }


def test_environment_required_and_scoped(client):
    c, calls, _ = client
    assert c.get("/v1/status", headers=headers()).status_code == 422
    assert c.get("/v1/status?environment=production", headers=headers()).status_code == 403
    assert c.get("/v1/status?environment=staging", headers=headers()).status_code == 200
    assert c.post("/v1/restart", json={"target": "api"}, headers=headers()).status_code == 422
    assert (
        c.post("/v1/restart", json=payload(environment="production"), headers=headers()).status_code
        == 403
    )
    assert c.post("/v1/restart", json=payload(), headers=headers(READ)).status_code == 403


def test_idempotency_and_conflict(client):
    c, _, _ = client
    one = c.post("/v1/restart", json=payload(), headers=headers())
    two = c.post("/v1/restart", json=payload(), headers=headers())
    assert one.status_code == two.status_code == 202
    assert one.json()["id"] == two.json()["id"]
    assert two.json()["idempotent_replay"] is True
    assert (
        c.post("/v1/restart", json=payload(target="worker"), headers=headers()).status_code == 409
    )


def test_audit_corruption_fails_closed(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)
    audit.append(AuditEvent("now", "test", "request", "principal", {}))
    path.write_text(path.read_text().replace('"test"', '"evil"'))
    with pytest.raises((ValueError, RuntimeError)):
        AuditLog(path)


def test_audit_failure_prevents_execution(client, monkeypatch):
    c, calls, app = client

    def fail(*a, **k):
        raise OSError("synthetic audit failure")

    monkeypatch.setattr(app.state.audit, "append", fail)
    assert c.post("/v1/restart", json=payload(), headers=headers()).status_code == 503
    assert not calls


def test_operation_disclosure_is_scoped(client):
    c, _, app = client
    op, _ = app.state.store.create(
        action="restart",
        environment="production",
        target="api",
        idempotency_key="private-production-key",
        requested_by="different-principal",
        request_id="test",
        params={},
    )
    assert c.get("/v1/operations/" + op.id, headers=headers()).status_code == 404
    assert c.get("/v1/operations?environment=production", headers=headers()).status_code == 403


def test_restart_is_unknown_not_rolled_back(tmp_path):
    from deepaha_ops.store import OperationStore

    path = tmp_path / "state.sqlite3"
    s = OperationStore(path)
    op, _ = s.create(
        action="restart",
        environment="staging",
        target="api",
        idempotency_key="interrupted-request",
        requested_by="test",
        request_id="test",
        params={},
    )
    s.mark_running(op.id)
    assert OperationStore(path).get(op.id).status == "UNKNOWN"


def test_runner_interruption_never_replays_on_restart(tmp_path, monkeypatch):
    import asyncio
    import time

    settings = configured(tmp_path)
    settings.queue_limit = 1
    app = create_app(settings)
    calls = []

    async def blocked(args):
        calls.append(args)
        await asyncio.Event().wait()

    monkeypatch.setattr(app.state.runner, "_run", blocked)
    with TestClient(app) as c:
        first = c.post("/v1/restart", json=payload(), headers=headers()).json()
        for _ in range(100):
            if calls:
                break
            time.sleep(0.01)
        assert len(calls) == 1
        second = c.post(
            "/v1/restart", json=payload(idempotency_key="queue-second"), headers=headers()
        )
        assert second.status_code == 202
        full = c.post("/v1/restart", json=payload(idempotency_key="queue-third"), headers=headers())
        assert full.status_code == 503
    restarted = create_app(settings)
    with TestClient(restarted) as c:
        result = c.get("/v1/operations/" + first["id"], headers=headers()).json()
        assert result["status"] == "UNKNOWN"
        replay = c.post("/v1/restart", json=payload(), headers=headers()).json()
        assert replay["id"] == first["id"] and replay["status"] == "UNKNOWN"
        assert len(calls) == 1
