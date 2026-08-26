import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from deepaha.local_human_test.provider_config import (
    LocalProviderConfigStore,
    ProviderConfigError,
    ProviderConfigIdempotencyConflict,
    SaveProviderConfig,
    WindowsDirectoryHardener,
)

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
SECRET = "synthetic-api-key-not-real"


class XorTestProtector:
    def protect(self, secret: bytes) -> bytes:
        return bytes(value ^ 0xA5 for value in secret)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return bytes(value ^ 0xA5 for value in ciphertext)


class RecordingHardener:
    def __init__(self, *, fail: bool = False) -> None:
        self.paths: list[Path] = []
        self._fail = fail

    def harden(self, path: Path) -> None:
        self.paths.append(path)
        if self._fail:
            raise ProviderConfigError("permission hardening failed")


def save_command(**overrides: object) -> SaveProviderConfig:
    values: dict[str, object] = {
        "provider": "deepseek",
        "base_url": "https://platform.example.invalid",
        "protocol": "openai_chat_completions",
        "model_id": "deepseek-v4-flash",
        "model_snapshot": "deepseek-v4-flash@configured",
        "provider_region": "cn",
        "zero_retention": True,
        "training_use": False,
        "supports_idempotency": False,
        "api_key": SecretStr(SECRET),
    }
    values.update(overrides)
    return SaveProviderConfig.model_validate(values)


def make_store(
    root: Path,
    *,
    hardener: RecordingHardener | None = None,
) -> LocalProviderConfigStore:
    return LocalProviderConfigStore(
        root=root,
        protector=XorTestProtector(),
        hardener=hardener or RecordingHardener(),
        clock=lambda: NOW,
    )


def test_store_round_trips_without_plaintext_or_secret_status(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    status = store.save(save_command(), idempotency_key="save-provider-1")
    raw = (tmp_path / "provider.json").read_bytes()

    assert SECRET.encode() not in raw
    assert "api_key" not in status.model_dump()
    assert status.model_dump(mode="json") == {
        "configured": True,
        "provider": "deepseek",
        "base_url": "https://platform.example.invalid",
        "protocol": "openai_chat_completions",
        "model_id": "deepseek-v4-flash",
        "model_snapshot": "deepseek-v4-flash@configured",
        "provider_region": "cn",
        "zero_retention": True,
        "training_use": False,
        "supports_idempotency": False,
        "egress_ready": True,
        "updated_at": "2026-08-26T12:00:00Z",
    }
    resolved = store.load_for_invocation()
    assert resolved.api_key.get_secret_value() == SECRET
    assert SECRET not in repr(resolved)
    assert SECRET not in repr(save_command())


def test_legacy_configuration_defaults_to_egress_denied(tmp_path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "provider": "deepseek",
        "base_url": "https://platform.example.invalid",
        "protocol": "openai_chat_completions",
        "model_id": "deepseek-v4-flash",
        "model_snapshot": "deepseek-v4-flash@configured",
        "protected_api_key": None,
        "updated_at": "2026-08-26T12:00:00Z",
    }
    (tmp_path / "provider.json").write_text(json.dumps(payload), encoding="utf-8")

    status = make_store(tmp_path).status()

    assert status.provider_region == "unknown"
    assert status.zero_retention is False
    assert status.training_use is True
    assert status.egress_ready is False


def test_public_official_provider_is_ready_without_zero_retention(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    status = store.save(
        save_command(zero_retention=False, training_use=False),
        idempotency_key="save-transient-provider",
    )

    assert status.configured is True
    assert status.zero_retention is False
    assert status.training_use is False
    assert status.egress_ready is True


def test_public_official_provider_is_ready_when_training_policy_is_unknown(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)

    status = store.save(
        save_command(zero_retention=False, training_use=True),
        idempotency_key="save-public-provider-with-unknown-training-policy",
    )

    assert status.configured is True
    assert status.provider_region == "cn"
    assert status.training_use is True
    assert status.egress_ready is True


def test_save_hardens_directory_before_writing(tmp_path: Path) -> None:
    hardener = RecordingHardener()
    store = make_store(tmp_path, hardener=hardener)

    store.save(save_command(), idempotency_key="save-provider-1")

    assert hardener.paths == [tmp_path]
    assert (tmp_path / "provider.json").is_file()


def test_hardener_failure_leaves_no_configuration(tmp_path: Path) -> None:
    store = make_store(tmp_path, hardener=RecordingHardener(fail=True))

    with pytest.raises(ProviderConfigError, match="permission hardening failed"):
        store.save(save_command(), idempotency_key="save-provider-1")

    assert not (tmp_path / "provider.json").exists()


def test_atomic_replace_failure_preserves_existing_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path)
    store.save(
        save_command(model_id="model-before"),
        idempotency_key="save-provider-before",
    )
    original = (tmp_path / "provider.json").read_bytes()

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr("deepaha.local_human_test.provider_config.os.replace", fail_replace)
    with pytest.raises(ProviderConfigError, match="configuration write failed"):
        store.save(
            save_command(model_id="model-after"),
            idempotency_key="save-provider-after",
        )

    assert (tmp_path / "provider.json").read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.invalid",
        "https://user:password@example.invalid",
        "https://example.invalid?key=value",
        "https://example.invalid/#fragment",
    ],
)
def test_provider_configuration_rejects_unsafe_urls(base_url: str) -> None:
    with pytest.raises(ValidationError):
        save_command(base_url=base_url)


def test_delete_secret_keeps_public_fields_and_fails_closed(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.save(save_command(), idempotency_key="save-provider-1")

    status = store.delete_secret()
    stored = json.loads((tmp_path / "provider.json").read_text(encoding="utf-8"))

    assert status.configured is False
    assert status.model_id == "deepseek-v4-flash"
    assert "protected_api_key" not in stored
    with pytest.raises(ProviderConfigError, match="Provider secret is not configured"):
        store.load_for_invocation()


def test_corrupt_or_undecryptable_configuration_fails_without_secret_echo(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.save(save_command(), idempotency_key="save-provider-1")
    (tmp_path / "provider.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ProviderConfigError) as captured:
        store.load_for_invocation()

    assert SECRET not in str(captured.value)


def test_windows_hardener_builds_a_shell_free_current_user_acl_command(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(arguments: list[str]) -> tuple[int, str]:
        calls.append(arguments)
        if arguments == ["whoami"]:
            return 0, "WORKSTATION\\tester\n"
        return 0, "processed"

    WindowsDirectoryHardener(runner=runner).harden(tmp_path)

    assert calls == [
        ["whoami"],
        [
            "icacls",
            str(tmp_path),
            "/inheritance:r",
            "/grant:r",
            "WORKSTATION\\tester:(OI)(CI)(F)",
            "*S-1-5-18:(OI)(CI)(F)",
        ],
    ]


def test_save_is_durably_idempotent_and_rejects_same_key_with_different_body(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    command = save_command()

    first = store.save(command, idempotency_key="save-provider-idempotent")
    original = (tmp_path / "provider.json").read_bytes()
    repeated = store.save(command, idempotency_key="save-provider-idempotent")

    assert repeated == first
    assert (tmp_path / "provider.json").read_bytes() == original

    with pytest.raises(
        ProviderConfigIdempotencyConflict,
        match="PROVIDER_CONFIG_IDEMPOTENCY_CONFLICT",
    ):
        store.save(
            save_command(model_id="different-model"),
            idempotency_key="save-provider-idempotent",
        )

    assert (tmp_path / "provider.json").read_bytes() == original
    assert SECRET.encode() not in original
    assert b"save-provider-idempotent" not in original
