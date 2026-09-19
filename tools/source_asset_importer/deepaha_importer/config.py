"""Non-secret preferences. Tokens remain in memory or OS environment only."""
from dataclasses import asdict
from pathlib import Path
import json
import os
import tempfile
from .client import ClientConfig
from .contract import parse_json
from .errors import ImporterError


def default_data_dir() -> Path:
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
        return Path(os.environ['LOCALAPPDATA']) / 'DeepAhaSourceImporter'
    return Path.home() / '.deepaha-source-importer'


def load_config(path) -> ClientConfig:
    path = Path(path)
    if not path.is_file(): return ClientConfig('')
    raw = parse_json(path.read_bytes(), 10000)
    if not isinstance(raw, dict): raise ImporterError('CONFIG_INVALID', '配置文件必须为对象。')
    allowed = set(ClientConfig.__dataclass_fields__)
    if set(raw) - allowed:
        raise ImporterError('CONFIG_INVALID', '配置中出现未支持字段（配置不应含有凭据）。')
    return ClientConfig(**raw)


def save_config(config: ClientConfig, path):
    if config.base_url: config.validate()
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(asdict(config), stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
