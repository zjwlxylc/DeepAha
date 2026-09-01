from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.artifacts.object_store import ObjectIntegrityError, ObjectMetadata

BUCKET = "deepaha-raw"
KEY = "live/2026/item.json"
CONTENT = b"official-public-content"
DIGEST = sha256(CONTENT).hexdigest()


def make_store(root: Path) -> LocalFileObjectStore:
    return LocalFileObjectStore(root=root, bucket=BUCKET)


def put(
    store: LocalFileObjectStore,
    *,
    key: str = KEY,
    content: bytes = CONTENT,
) -> ObjectMetadata:
    return store.put_bytes_if_absent(
        key=key,
        content=content,
        media_type="application/json",
        sha256=sha256(content).hexdigest(),
    )


def test_local_store_persists_and_verifies_bytes_across_instances(tmp_path: Path) -> None:
    first = make_store(tmp_path)

    metadata = put(first)
    second = make_store(tmp_path)

    assert metadata.bucket == BUCKET
    assert metadata.key == KEY
    assert metadata.byte_size == len(CONTENT)
    assert metadata.sha256 == DIGEST
    assert metadata.media_type == "application/json"
    assert second.get_bytes(key=KEY) == CONTENT
    assert second.stat(key=KEY) == metadata


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../secret",
        "/absolute",
        "C:/absolute",
        "a/../../b",
        "a\\..\\b",
        "a//b",
        "./a",
        "a/.",
    ],
)
def test_local_store_rejects_noncanonical_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError, match="canonical relative path"):
        make_store(tmp_path).stat(key=key)


def test_local_store_rejects_caller_hash_mismatch_before_writing(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    with pytest.raises(ObjectIntegrityError, match="caller-supplied SHA-256"):
        store.put_bytes_if_absent(
            key=KEY,
            content=CONTENT,
            media_type="application/json",
            sha256="0" * 64,
        )

    assert not (tmp_path / BUCKET / "objects" / KEY).exists()


def test_same_key_same_bytes_is_idempotent_but_different_bytes_conflict(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = put(store)

    assert put(make_store(tmp_path)) == first
    with pytest.raises(ObjectIntegrityError, match="existing object does not match"):
        put(make_store(tmp_path), content=b"different-official-content")
    assert store.get_bytes(key=KEY) == CONTENT


def test_metadata_or_content_tampering_is_detected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    put(store)
    metadata_path = tmp_path / BUCKET / "metadata" / f"{KEY}.json"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace(DIGEST, "f" * 64),
        encoding="utf-8",
    )

    with pytest.raises(ObjectIntegrityError, match="stored SHA-256"):
        store.get_bytes(key=KEY)


def test_concurrent_different_writes_never_overwrite_the_winner(tmp_path: Path) -> None:
    contents = (b"first" * 100_000, b"second" * 100_000)

    def attempt(content: bytes) -> ObjectMetadata | ObjectIntegrityError:
        try:
            return put(make_store(tmp_path), content=content)
        except ObjectIntegrityError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, contents))

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, ObjectIntegrityError)]
    assert len(successes) == 1
    assert len(failures) == 1
    stored = make_store(tmp_path).get_bytes(key=KEY)
    assert stored in contents


def test_unheld_lock_file_from_a_previous_process_does_not_block_recovery(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    store.ensure_bucket()
    lock_path = tmp_path / BUCKET / ".locks" / sha256(KEY.encode("utf-8")).hexdigest()
    lock_path.write_bytes(b"\0")

    metadata = put(store)

    assert metadata.sha256 == DIGEST
    assert store.get_bytes(key=KEY) == CONTENT


def test_publish_failure_leaves_no_partial_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path)

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic publish failure")

    monkeypatch.setattr("deepaha.artifacts.local_file.os.replace", fail_replace)
    with pytest.raises(ObjectIntegrityError, match="object publish failed"):
        put(store)

    assert not (tmp_path / BUCKET / "objects" / KEY).exists()
    assert not (tmp_path / BUCKET / "metadata" / f"{KEY}.json").exists()


def test_compensation_probe_and_delete_require_matching_hash(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    assert store.stat_if_present(key=KEY) is None
    metadata = put(store)
    assert store.stat_if_present(key=KEY) == metadata

    with pytest.raises(ObjectIntegrityError, match="refusing to delete"):
        store.delete_if_matches(key=KEY, sha256="f" * 64)
    assert store.get_bytes(key=KEY) == CONTENT

    assert store.delete_if_matches(key=KEY, sha256=DIGEST) is True
    assert store.stat_if_present(key=KEY) is None
    assert store.delete_if_matches(key=KEY, sha256=DIGEST) is False
