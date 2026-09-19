"""Create a source ZIP with an auditable manifest, excluding local data/secrets."""
from __future__ import annotations
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'__pycache__', '.git', '.venv', 'venv', '.pytest_cache', 'build', 'dist',
                 'receipts', 'pending', 'library_downloads', 'library_runs', 'library_diagnostics', 'library_research_downloads', 'research_workbench', 'exports', '.mypy_cache', '.ruff_cache'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.db', '.sqlite', '.sqlite3', '.key', '.pem', '.pfx', '.p12', '.ttf', '.otf', '.woff', '.woff2'}


def eligible(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if path.is_symlink() or not path.is_file():
        return False
    if any(part in EXCLUDED_DIRS or part.endswith('.egg-info') for part in relative.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name in {'settings.json', 'codex-library.settings.json', '.env', 'MANIFEST.sha256'}:
        return False
    return True


def build(destination: Path) -> dict:
    paths = sorted((p for p in ROOT.rglob('*') if eligible(p)), key=lambda p:p.relative_to(ROOT).as_posix())
    checksums = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest = ROOT / 'MANIFEST.sha256'
    manifest.write_text(''.join(f'{sha}  {name}\n' for name,sha in checksums.items()), encoding='utf-8')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths+[manifest]:
            archive.write(path, arcname=f'{ROOT.name}/{path.relative_to(ROOT).as_posix()}')
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('ZIP CRC verification failed')
        for name, sha in checksums.items():
            if hashlib.sha256(archive.read(f'{ROOT.name}/{name}')).hexdigest() != sha:
                raise RuntimeError(f'Archive content mismatch: {name}')
    archive_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix+'.sha256').write_text(f'{archive_hash}  {destination.name}\n',encoding='ascii')
    return {'zip_path':str(destination),'zip_sha256':archive_hash,'files':len(paths)+1,
            'zip_size_bytes':destination.stat().st_size,'crc_verified':True,'file_hashes_verified':True}


if __name__ == '__main__':
    dest = Path(sys.argv[1]) if len(sys.argv)>1 else ROOT.parent/(ROOT.name+'.zip')
    print(json.dumps(build(dest),ensure_ascii=False,indent=2))
