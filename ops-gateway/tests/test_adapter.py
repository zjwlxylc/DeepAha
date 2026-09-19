import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    if sys.platform == "win32":
        monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4))
    path = Path(__file__).parents[1] / "adapter/adapter.py"
    spec = importlib.util.spec_from_file_location("host_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.os, "geteuid", lambda: 0, raising=False)
    return module


@pytest.mark.parametrize(
    "args",
    [
        ["shell", "staging", "id"],
        ["status", "unknown"],
        ["status", "staging", "extra"],
        ["logs", "staging", "sshd", "20"],
        ["logs", "staging", "api", "501"],
        ["restart", "staging", "a" * 40, "all;id", "-"],
        ["deploy", "staging", "a" * 40, "main", "-"],
        ["backup", "staging", "a" * 40, "/tmp", "-"],
        ["restart", "production", "main", "all", "-"],
    ],
)
def test_host_boundary_rejects_without_running_commands(adapter, monkeypatch, args):
    monkeypatch.setattr(
        adapter, "load", lambda *_: pytest.fail("invalid input reached host config")
    )
    with pytest.raises(RuntimeError):
        adapter.main(args)


def test_receipt_bound_expiring_and_single_use(adapter, tmp_path, monkeypatch):
    import json
    import time

    monkeypatch.setattr(adapter, "REGISTRY", tmp_path)
    directory = tmp_path / "approvals"
    directory.mkdir()
    identifier = "a" * 32
    path = directory / (identifier + ".json")
    binding = {
        "action": "deploy",
        "environment": "production",
        "expected_current": "a" * 40,
        "target": "b" * 40,
    }

    def write(exp):
        path.write_text(json.dumps({"binding": binding, "expires_at": exp}))

    monkeypatch.setattr(adapter, "trusted", lambda p: p)
    write(time.time() + 60)
    with pytest.raises(RuntimeError, match="MISMATCH"):
        adapter.receipt(identifier, "deploy", "production", "c" * 40, "b" * 40)
    write(time.time() - 1)
    with pytest.raises(RuntimeError, match="EXPIRED"):
        adapter.receipt(identifier, "deploy", "production", "a" * 40, "b" * 40)
    write(time.time() + 60)
    adapter.receipt(identifier, "deploy", "production", "a" * 40, "b" * 40)
    with pytest.raises(FileNotFoundError):
        adapter.receipt(identifier, "deploy", "production", "a" * 40, "b" * 40)
