"""SQLite backup and empty-target restore. PostgreSQL uses pg_dump + raw volume.
Credentials are deliberately excluded. Restoring revokes saved login sessions.
"""
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile
from .errors import Problem

MAX_BACKUP_BYTES = 20 * 1024**3


def create_backup(database_url, object_root, destination):
    if not database_url.startswith('sqlite:///'):
        raise Problem('PostgreSQL请使用pg_dump与原件卷备份')
    destination=Path(destination);object_root=Path(object_root)
    if destination.exists():raise Problem('目标已存在，不覆盖备份')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        copied=Path(directory)/'database.sqlite'
        # Connections must be closed explicitly: the context manager only scopes
        # the transaction, and an open handle makes the temp directory undeletable
        # on Windows (WinError 32).
        source=sqlite3.connect(database_url[len('sqlite:///'):])
        try:
            with closing(sqlite3.connect(copied)) as target:
                source.backup(target)
        finally:
            source.close()
        members=[('database.sqlite',copied)]
        members += [('objects/'+p.relative_to(object_root).as_posix(),p) for p in object_root.rglob('*') if p.is_file() and '.locks' not in p.parts]
        with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as archive:
            hashes={}
            for name,path in members:
                archive.write(path,name)
                with path.open('rb') as handle:hashes[name]=hashlib.file_digest(handle,'sha256').hexdigest()
            archive.writestr('BACKUP_MANIFEST.json',json.dumps({'schema_version':1,'files':hashes,'credentials_included':False},indent=2))
    os.chmod(destination,0o600)
    return {'backup':str(destination),'files':len(hashes),'credentials_included':False}


def _manifest(archive):
    entries=archive.infolist();names=[e.filename for e in entries]
    if len(names)!=len(set(names)) or 'BACKUP_MANIFEST.json' not in names:raise Problem('备份目录不完整或重复')
    if sum(e.file_size for e in entries)>MAX_BACKUP_BYTES:raise Problem('备份超过20GB恢复上限')
    if archive.getinfo('BACKUP_MANIFEST.json').file_size>16*1024**2:raise Problem('备份清单过大')
    for entry in entries:
        name=entry.filename;path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path)!=name or '\\' in name or ':' in name or (entry.external_attr>>16)&0o170000==0o120000:
            raise Problem('备份中含不安全路径')
        if name not in ('database.sqlite','BACKUP_MANIFEST.json') and not name.startswith('objects/'):
            raise Problem('备份包含未许可文件')
    try:manifest=json.loads(archive.read('BACKUP_MANIFEST.json'))
    except (ValueError,KeyError):raise Problem('备份清单无法读取')
    if manifest.get('schema_version')!=1 or not isinstance(manifest.get('files'),dict):raise Problem('备份版本不兼容')
    if set(manifest['files'])!=set(names)-{'BACKUP_MANIFEST.json'} or 'database.sqlite' not in manifest['files']:raise Problem('备份文件与清单不一致')
    return manifest


def verify_backup(path):
    try:
        with zipfile.ZipFile(path) as archive:
            manifest=_manifest(archive)
            for name,digest in manifest['files'].items():
                with archive.open(name) as source:
                    if hashlib.file_digest(source,'sha256').hexdigest()!=digest:raise Problem('备份校验失败：'+name)
    except (zipfile.BadZipFile,OSError) as e:raise Problem('无法读取有效备份文件') from e
    return {'backup_valid':True,'files':len(manifest['files'])}


def restore_backup(path, destination):
    destination=Path(destination).resolve()
    if destination.exists():raise Problem('恢复目录必须尚不存在；不会覆盖现有数据')
    verify_backup(path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.deepaha-restore-',dir=destination.parent) as parent:
        stage=Path(parent)/'data';stage.mkdir(mode=0o700)
        with zipfile.ZipFile(path) as archive:
            manifest=_manifest(archive)
            for name in manifest['files']:
                target=stage/('deepaha.db' if name=='database.sqlite' else name)
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(name) as src,target.open('xb') as dst:
                    while block:=src.read(1024**2):dst.write(block)
        database=stage/'deepaha.db'
        # `with c:` commits the session-revoking writes; the explicit close releases
        # the handle so the staged directory can be renamed on Windows.
        c=sqlite3.connect(database)
        try:
            with c:
                if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Problem('备份数据库完整性检查失败')
                if c.execute("SELECT value FROM product_meta WHERE key='schema_version'").fetchone()!=('1',):raise Problem('备份数据库版本不兼容')
                c.execute('UPDATE product_sessions SET revoked=1')
                c.execute("DELETE FROM product_meta WHERE key='worker_heartbeat'")
        except sqlite3.DatabaseError as e:raise Problem('备份数据库不可恢复') from e
        finally:
            c.close()
        # Recheck destination immediately before the atomic directory rename.
        if destination.exists():raise Problem('恢复目录已被其他进程创建')
        os.rename(stage,destination)
    return {'restored':str(destination),'sessions_revoked':True,'credentials_restored':False}
