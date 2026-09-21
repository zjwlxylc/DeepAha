"""Real filesystem contention: local retry, never retry remote investigation."""
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.product.storage import ArchiveStore


def _held(store, content):
    digest=hashlib.sha256(content).hexdigest();key=f'{digest[:2]}/{digest}'
    lock=store.backend._lock_root / hashlib.sha256(key.encode()).hexdigest()
    return store.backend._acquire_lock(lock)


def test_local_shared_object_waits_then_saves_without_partial_bytes(tmp_path):
    store=ArchiveStore(tmp_path/'objects');content=b'same fixture attachment';fd=_held(store,content)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(store.save,{'attachment.txt':content})
        try:
            time.sleep(.12)
            assert not future.done(), 'A short local write lock must not fail the investigation'
        finally:store.backend._release_lock(fd)
        manifest=future.result(timeout=4)
    assert store.one(manifest,'attachment.txt')==content
    assert store.save({'attachment.txt':content})==manifest


def test_corrupt_content_is_not_treated_as_lock_contention(tmp_path,monkeypatch):
    import deepaha.product.storage as module
    store=ArchiveStore(tmp_path/'objects');manifest=store.save({'attachment.txt':b'original'})
    item=manifest['attachment.txt'];path=store.backend._object_root/item['key'];path.write_bytes(b'tampered')
    def no_wait(*args):raise AssertionError('Integrity errors must not be retried')
    monkeypatch.setattr(time,'sleep',no_wait)
    with pytest.raises(ObjectIntegrityError,match='SHA-256'):store.save({'attachment.txt':b'original'})


def test_local_lock_wait_is_bounded_and_retains_lock(tmp_path):
    store=ArchiveStore(tmp_path/'objects');content=b'held permanently';fd=_held(store,content);started=time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(store.save,{'attachment.txt':content})
            with pytest.raises(ObjectIntegrityError,match='already in progress'):future.result(timeout=5)
        assert 1.9 <= time.monotonic()-started < 4.5
    finally:store.backend._release_lock(fd)
