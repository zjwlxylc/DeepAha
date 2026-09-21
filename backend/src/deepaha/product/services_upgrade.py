"""R3 additive membership migration. Stopped API/worker; backup before first DDL."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from sqlalchemy import inspect, select, func
from sqlalchemy.engine import make_url
from deepaha_membership.db import Store, metadata
from deepaha_membership.errors import DomainError
from .models import Task, Meta
from .backup import create_backup, verify_backup
from .errors import Problem


def pg_backup(product, path):
    # No password in argv/logs. Dump and all objects are hashed before schema writes.
    if path.exists():raise Problem('备份路径已存在，拒绝覆盖',409)
    if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
        raise Problem('请安装与服务器版本兼容的pg_dump和pg_restore',409,'POSTGRES_TOOLS_REQUIRED')
    path.mkdir(parents=True,mode=0o700)
    u=make_url(product.database_url)
    env={**os.environ,'PGHOST':u.host or 'localhost','PGPORT':str(u.port or 5432),
         'PGUSER':u.username or '', 'PGPASSWORD':u.password or '', 'PGDATABASE':u.database or ''}
    for key in ('sslmode','sslrootcert','sslcert','sslkey'):
        if key in u.query:env['PG'+key.upper()]=str(u.query[key])
    try:
        with (path/'database.dump').open('xb') as out:
            subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl'],env=env,stdout=out,stderr=subprocess.PIPE,check=True,timeout=600)
        subprocess.run(['pg_restore','--list',str(path/'database.dump')],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=60)
        with tarfile.open(path/'objects.tar.gz','w:gz') as archive:
            if product.object_root.exists():
                archive.add(product.object_root,arcname='objects',filter=lambda info:None if '.locks' in Path(info.name).parts else info)
        hashes={}
        for f in (path/'database.dump',path/'objects.tar.gz'):
            f.chmod(0o600)
            with f.open('rb') as stream:hashes[f.name]=hashlib.file_digest(stream,'sha256').hexdigest()
        receipt={'files':hashes,'credentials_included':False,'schema_started':False,
                 'verified':'pg_restore --list; SHA256; restore drill still required'}
        with (path/'BACKUP_MANIFEST.json').open('x',encoding='utf-8') as out:
            json.dump(receipt,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
    except (OSError,subprocess.SubprocessError):
        raise Problem('备份失败，未升级。请检查磁盘、数据库连接和宿主备份工具',503,'BACKUP_FAILED') from None
    return {'backup':str(path),'backup_verified':True,'restore_drill_verified':False}


def upgrade_services(product, backup_path):
    present=set(inspect(product.db.engine).get_table_names())
    if 'product_meta' not in present:raise Problem('新安装请使用setup；本命令仅升级已有R2产品库',409)
    found=set(metadata.tables)&present
    if found:
        try:Store(product.db.engine).assert_ready()
        except DomainError as e:raise Problem(e.message,409,e.code) from None
        return {'already_current':True,'data_modified':False,'wma_called':False}
    with product.db.tx(False) as s:
        version=s.get(Meta,'schema_version')
        if not version or version.value!='1':raise Problem('宿主数据库版本不兼容',409,'SCHEMA_MISMATCH')
        if s.scalar(select(func.count()).select_from(Task).where(Task.status=='RUNNING')):
            raise Problem('仍有运行中任务，请先核查远端并停止工作进程',409,'ACTIVE_WORK')
    path=Path(backup_path)
    if product.db.engine.dialect.name=='sqlite':
        result=create_backup(product.database_url,product.object_root,path)
        verify_backup(path);result.update(backup_verified=True,restore_drill_verified=False)
    elif product.db.engine.dialect.name=='postgresql':result=pg_backup(product,path)
    else:raise Problem('仅支持SQLite/PostgreSQL',409)
    from .membership import initialize
    initialize(product)
    Store(product.db.engine).assert_ready()
    return {**result,'already_current':False,'data_modified':True,'added_tables':sorted(metadata.tables),
            'membership_schema_version':'1','plans':'DRAFT','automatic_collection':False,
            'wma_called':False,'old_facts_modified':False,'passwords_changed':False}
