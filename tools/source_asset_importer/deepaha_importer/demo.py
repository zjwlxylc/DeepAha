"""Explicit local rehearsal. Does not touch DeepAha, WMA or ChatGPT Library."""
from pathlib import Path
import os
import secrets
from .client import LocalClient
from .errors import ImporterError
from .repository import SQLiteRepository
from .security import Principal, TokenSigner
from .service import ImportService


def demo_client(directory):
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path = directory / 'demo-signing.key'
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        secret = key_path.read_bytes()
    else:
        secret = secrets.token_bytes(32)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(secret); stream.flush(); os.fsync(stream.fileno())
    if len(secret) != 32:
        raise ImporterError('DEMO_KEY_INVALID', '演练签名文件不完整；请换一个新的演练目录。', 500)
    repository = SQLiteRepository(directory / 'demo.sqlite3'); repository.initialize()
    principal = Principal('local-demo-user', 'source-scout', frozenset({'scout:preview', 'scout:import', 'scout:read'}))
    service = ImportService(repository, TokenSigner(secret), 'DEMO')
    return LocalClient(service, principal)
