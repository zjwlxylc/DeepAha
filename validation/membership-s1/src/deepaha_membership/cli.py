"""Explicit backup/init and bounded scheduled ticks; no scheduler auto-installation."""
from pathlib import Path
import argparse,hashlib,json,os,sqlite3
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from .db import Store
from .commerce import Commerce
from .errors import require
from .auth import Actor
from .tracking import Tracking,ACTIVE_JOBS
from .integration import ProductPort


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def initialize_database(database_url,backup_path):
    url=make_url(database_url);driver=url.get_backend_name();backup=Path(backup_path)
    backup.parent.mkdir(parents=True,exist_ok=True)
    manifest=backup.with_name(backup.name+'.manifest.json')
    if manifest.exists():raise FileExistsError('备份回执已存在，请使用新的备份名称')
    if driver=='sqlite':
        source=Path(url.database or '')
        if not source.is_file():raise ValueError('请输入已初始化的宿主数据库文件；独立体验请运行demo')
        if backup.exists():raise FileExistsError('备份文件已存在，拒绝覆盖')
        if source.resolve()==backup.resolve():raise ValueError('备份不能覆盖源数据库')
        backup.touch(exist_ok=False)
        backup.chmod(0o600)
        with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(backup) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite备份完整性检查未通过')
        backup_kind='SQLITE_ONLINE_BACKUP_CHECKED'
    elif driver=='postgresql':
        if not backup.is_file() or backup.stat().st_size==0:raise ValueError('PostgreSQL须先通过原运维流程生成非空备份文件，并在预生产做恢复演练')
        backup_kind='EXTERNAL_BACKUP_BYTES_ONLY_NOT_RESTORE_VERIFIED'
    else:raise ValueError('本模块仅设计支持SQLite/PostgreSQL；其他数据库不执行升级')
    receipt={'database_driver':driver,'backup_file':backup.name,'backup_sha256':file_sha(backup),'backup_bytes':backup.stat().st_size,'backup_kind':backup_kind,'migration_started':False}
    with manifest.open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
    # Backup manifest is safely persisted before any membership DDL is executed.
    engine=create_engine(database_url)
    try:
        store=Store(engine);store.initialize();Commerce(store).seed()
    finally:engine.dispose()
    result={**receipt,'migration_started':True,'membership_schema':'1','catalog':'DRAFT_DEFAULTS'}
    manifest.with_name(manifest.stem+'.result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def tick(product,settings,operator,*,allow_site_enqueue=False,max_jobs=3,connection='default'):
    require(type(max_jobs) is int and 1<=max_jobs<=20,'本轮网站任务上限应为1至20')
    # A CLI-supplied name does not manufacture roles: recheck the real account.
    with product.db.tx(False) as session:product._account(session,operator,'operator')
    a=Actor(operator,frozenset({'operator'}));s=Store(product.db.engine);s.assert_ready()
    tracking=Tracking(s,Commerce(s),ProductPort(product,settings))
    result={'topics':tracking.scan_topics(a),'site_publications':tracking.scan_site_publications(a),'refreshed':[],'dispatched':[],'skipped':[]}
    for job in tracking.list_jobs(a,manage=True):
        if job['state'] in ('CORE_QUEUED','CORE_RUNNING') and job['core_task_id']:
            try:result['refreshed'].append(tracking.refresh(a,job['id']))
            except Exception as e:result['skipped'].append({'job':job['id'],'code':getattr(e,'code','REFRESH_FAILED')})
    # Explicit paid-action opt-in is required for EACH invocation/scheduled command.
    # Unknown-result retries are operator-driven, never automatically looped.
    if allow_site_enqueue:
        for w in tracking.mine(a,manage=True):
            if len(result['dispatched'])>=max_jobs:break
            if w['kind']!='SITE' or not w['effective']:continue
            try:
                from .errors import DomainError
                job=tracking.prepare(a,w['id'],connection,'tick-'+s.time()+'-'+w['id'])
                if job['state']!='QUEUED':continue
                result['dispatched'].append(tracking.dispatch(a,job['id']))
            except Exception as e:result['skipped'].append({'watch':w['id'],'code':getattr(e,'code','SITE_NOT_READY')})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--from-core',action='store_true');init.add_argument('--backup',required=True)
    run=sub.add_parser('tick');run.add_argument('--operator',required=True);run.add_argument('--allow-site-enqueue',action='store_true');run.add_argument('--max-jobs',type=int,default=3);run.add_argument('--connection',default='default')
    args=p.parse_args()
    if args.command=='init':
        if args.from_core:
            from deepaha.product.config import Settings
            url=Settings.from_env().database_url
        else:
            url=os.getenv('MEMBERSHIP_DATABASE_URL')
            if not url:p.error('请设置MEMBERSHIP_DATABASE_URL，或在原项目环境使用--from-core')
        result=initialize_database(url,args.backup)
    else:
        from deepaha.product.config import Settings
        from deepaha.product.service import Product
        settings=Settings.from_env();product=Product(settings.database_url,settings.data_dir/'objects')
        try:result=tick(product,settings,args.operator,allow_site_enqueue=args.allow_site_enqueue,max_jobs=args.max_jobs,connection=args.connection)
        finally:product.db.engine.dispose()
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
