"""Explicit initialization, account maintenance, file intake and worker commands."""
import argparse
import asyncio
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import zipfile
from .config import Settings,ConnectionConfig
from .service import Product
from .errors import Problem


def output(v):print(json.dumps(v,ensure_ascii=False,indent=2,default=str))

def main(argv=None):
    ap=argparse.ArgumentParser(prog='deepaha',description='DeepAha 机会星图：初始化、账号、采集、导入和备份')
    sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('init',help='仅新增当前产品所需数据表，不改写旧表')
    sub.add_parser('upgrade-access',help='已完成宿主备份后，显式新增邀请码表；不改现有业务表')
    admin=sub.add_parser('access-operator');admin.add_argument('username',help='显式授予已有账号operator角色')
    upgrade=sub.add_parser('upgrade',help='备份并补齐rc2来源资产表，保留所有原有数据');upgrade.add_argument('--backup',type=Path)
    sg1=sub.add_parser('upgrade-sg1',help='备份并升级为SG1岗位/赛道级机会总览');sg1.add_argument('--backup',type=Path)
    sg51=sub.add_parser('upgrade-sg5-1',help='备份并刷新SG5.1证据支持的时间节点，不重新调用WMA');sg51.add_argument('--backup',type=Path)
    sg6=sub.add_parser('upgrade-sg6',help='备份并增加SG6行动时间线与反馈候选表');sg6.add_argument('--backup',type=Path)
    sg62=sub.add_parser('upgrade-sg6-2',help='备份并刷新SG6.2资格证据编译派生投影，不恢复逐字段审核');sg62.add_argument('--backup',type=Path)
    sg7=sub.add_parser('upgrade-sg7',help='备份并增加SG7 Opportunity Lab隔离实验表，不改正式事实/审核结果');sg7.add_argument('--backup',type=Path)
    sub.add_parser('setup',help='交互初始化并开通拥有审核/维护权限的首个账号')
    u=sub.add_parser('user-add');u.add_argument('username');u.add_argument('--roles',default='user');u.add_argument('--password-env',help='从指定环境变量读取密码，不在命令行传明文')
    revoke=sub.add_parser('user-disable');revoke.add_argument('username')
    reset=sub.add_parser('password-reset');reset.add_argument('username')
    source=sub.add_parser('source-add');source.add_argument('--actor',required=True);source.add_argument('--name',required=True);source.add_argument('--url',required=True);source.add_argument('--brief-file');source.add_argument('--allowed-host',action='append',default=[])
    identity=sub.add_parser('identity-adopt');identity.add_argument('--source',required=True);identity.add_argument('--notice-url',required=True);identity.add_argument('--public-id',required=True);identity.add_argument('--source-record-key');identity.add_argument('--actor',required=True)
    sources=sub.add_parser('source-import');sources.add_argument('file',type=Path);sources.add_argument('--actor',required=True)
    ingest=sub.add_parser('intake');ingest.add_argument('file',type=Path);ingest.add_argument('--source',required=True);ingest.add_argument('--actor',required=True);ingest.add_argument('--notice-url')
    examples=sub.add_parser('examples');examples.add_argument('--actor',required=True);examples.add_argument('--output',type=Path,help='只生成虚构体验数据文件，不入库')
    worker=sub.add_parser('worker');worker.add_argument('--once',action='store_true');worker.add_argument('--schedule-as',help='用该维护账号执行已授权的周期检查');worker.add_argument('--isolated-fixture-mode',action='store_true',help='Only heartbeat: disable schedules and remote clients in isolated tests')
    server=sub.add_parser('serve');server.add_argument('--host',default='127.0.0.1');server.add_argument('--port',type=int,default=8000)
    backup=sub.add_parser('backup');backup.add_argument('file',type=Path)
    verify=sub.add_parser('verify-backup');verify.add_argument('file',type=Path)
    restore=sub.add_parser('restore-backup');restore.add_argument('file',type=Path);restore.add_argument('--target',type=Path,required=True)
    migrate=sub.add_parser('migrate-sqlite-backup',help='将已校验的本地SQLite备份迁移到空PostgreSQL；不迁移WMA密钥');migrate.add_argument('file',type=Path);migrate.add_argument('--report',type=Path)
    sub.add_parser('deploy-check',help='只读检查当前生产环境、PostgreSQL、账号、对象目录和WMA配置')
    legacy=sub.add_parser('legacy-inventory');legacy.add_argument('--output',type=Path)
    export=sub.add_parser('legacy-export');export.add_argument('task_id');export.add_argument('--object-root',type=Path,required=True);export.add_argument('--bucket',default='deepaha-raw');export.add_argument('--output',type=Path,required=True)
    args=ap.parse_args(argv)
    settings=Settings.from_env();settings.data_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    p=Product(settings.database_url,settings.data_dir/'objects')
    try:
        if args.command in ('init','setup'):
            p.initialize();output({'initialized':True,'data_dir':str(settings.data_dir)})
            if args.command=='setup':
                name=input('首个账号（英文或数字，默认 owner）: ').strip() or 'owner'
                password=getpass.getpass('密码（至少4个字符）: ')
                if getpass.getpass('再次输入密码: ')!=password:raise Problem('两次密码不一致')
                output(p.create_account(name,password,['user','reviewer','operator']))
        elif args.command=='upgrade-access':
            from .models import Base,ACCESS_TABLE_NAMES
            Base.metadata.create_all(p.db.engine,tables=[t for t in Base.metadata.sorted_tables if t.name in ACCESS_TABLE_NAMES])
            result=p.migrate_access_roles()
            output({'access_schema':'2','added_tables':sorted(ACCESS_TABLE_NAMES),'migrated_accounts':result['migrated_accounts'],'passwords_changed':False})
        elif args.command=='access-operator':
            from sqlalchemy import select
            from .models import Account
            from .access import _revoke_sessions
            with p.db.tx() as s:
                account=s.scalar(select(Account).where(Account.username==args.username,Account.active.is_(True)))
                if not account:raise Problem('指定账号不存在或已停用',404)
                account.roles=list(dict.fromkeys([r for r in account.roles if r!='admin']+['operator']))
                _revoke_sessions(s,account.id)
                p._audit(s,'SYSTEM_CLI','ACCESS_OPERATOR_GRANT',account.id,'显式授予账号管理权限')
            output({'operator_granted':True})
        elif args.command=='upgrade':
            from .upgrade import upgrade_source_intake
            from .models import now
            target=args.backup or settings.data_dir/'backups'/('before-source-intake-'+now().strftime('%Y%m%dT%H%M%S%f')+'.zip')
            output(upgrade_source_intake(p,target))
        elif args.command=='upgrade-sg1':
            from .upgrade import upgrade_actionable_catalog
            from .models import now
            target=args.backup or settings.data_dir/'backups'/('before-sg1-'+now().strftime('%Y%m%dT%H%M%S%f')+'.zip')
            output(upgrade_actionable_catalog(p,target))
        elif args.command=='upgrade-sg5-1':
            from .upgrade import upgrade_time_semantics
            from .models import now
            target=args.backup or settings.data_dir/'backups'/('before-sg5-1-'+now().strftime('%Y%m%dT%H%M%S%f')+'.zip')
            output(upgrade_time_semantics(p,target))
        elif args.command=='upgrade-sg6':
            from .upgrade import upgrade_action_loop
            from .models import now
            target=args.backup or settings.data_dir/'backups'/('before-sg6-'+now().strftime('%Y%m%dT%H%M%S%f')+'.zip')
            output(upgrade_action_loop(p,target))
        elif args.command=='upgrade-sg6-2':
            from .upgrade import upgrade_qualification_compiler
            from .models import now
            target=args.backup or settings.data_dir/'backups'/('before-sg6-2-'+now().strftime('%Y%m%dT%H%M%S%f')+'.zip')
            output(upgrade_qualification_compiler(p,target))
        elif args.command=='upgrade-sg7':
            from .upgrade import upgrade_opportunity_lab
            from .models import now
            target=args.backup or settings.data_dir/'backups'/('before-sg7-'+now().strftime('%Y%m%dT%H%M%S%f')+'.zip')
            output(upgrade_opportunity_lab(p,target))
        elif args.command=='user-add':
            pw=os.environ.get(args.password_env,'') if args.password_env else getpass.getpass('账号密码（至少4个字符）: ')
            output(p.create_account(args.username,pw,args.roles.split(',')))
        elif args.command=='user-disable':p.revoke_account(args.username);output({'disabled':args.username})
        elif args.command=='password-reset':
            from sqlalchemy import select
            from .models import Account,LoginSession,PasswordReset
            from .auth import password_hash
            value=getpass.getpass('新密码（至少4个字符）: ')
            if getpass.getpass('再次输入新密码: ')!=value:raise Problem('两次密码不一致')
            with p.db.tx() as s:
                account=s.scalar(select(Account).where(Account.username==args.username))
                if not account:raise Problem('账号不存在',404)
                account.password_hash=password_hash(value)
                for r in s.scalars(select(LoginSession).where(LoginSession.account_id==account.id)):r.revoked=True
                for r in s.scalars(select(PasswordReset).where(PasswordReset.account_id==account.id)):r.used=True
                p._audit(s,'SYSTEM_CLI','PASSWORD_RESET',account.id,'更改密码并撤销全部会话')
            output({'password_reset':True})
        elif args.command=='identity-adopt':output(p.adopt_identity(args.source,args.notice_url,args.public_id,actor=args.actor,source_record_key=args.source_record_key))
        elif args.command=='source-add':output(p.add_source(args.name,args.url,actor=args.actor,allowed_hosts=args.allowed_host,brief=args.brief_file and Path(args.brief_file).read_text(encoding='utf-8') or ''))
        elif args.command=='source-import':output(p.import_sources(json.loads(args.file.read_text(encoding='utf-8-sig')),actor=args.actor))
        elif args.command=='intake':
            r=p.ingest(args.source,args.file.read_bytes(),actor=args.actor,notice_url=args.notice_url)
            output({'revision_id':r['id'],'can_approve':r['can_approve'],'review_path':'/review/packet/'+r['id']})
        elif args.command=='examples':
            from .examples import bundles
            if args.output:
                args.output.mkdir(parents=True,exist_ok=True)
                for name,b in bundles():(args.output/name).write_bytes(b)
                output({'fictional_examples_directory':str(args.output),'database_modified':False})
            else:
                source=p.add_source('澄川机会体验来源','https://institute.example.org/',actor=args.actor)
                out=[]
                for name,b in bundles():
                    r=p.ingest(source['id'],b,actor=args.actor);out.append({'file':name,'review_path':'/review/packet/'+r['id']})
                output({'fictional_examples_only':True,'automatic_approvals':0,'results':out})
        elif args.command=='serve':
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(settings,product=p),host=args.host,port=args.port,access_log=True)
        elif args.command=='worker':
            from .worker import run_once,schedule_due
            async def loop():
                while True:
                    try:
                        from .worker import schedule_weekly_digests
                        if not args.isolated_fixture_mode:schedule_weekly_digests(p)
                        factory=None if args.isolated_fixture_mode else ConnectionConfig(settings.data_dir,settings.mode).factory()
                        if factory:schedule_due(p,args.schedule_as)
                        result=await run_once(p,client_factory=factory)
                        if args.once or result['state'] not in ('IDLE','NOT_CONFIGURED'):output(result)
                    except KeyboardInterrupt:return
                    except Exception as e:
                        output({'state':'WORKER_UNAVAILABLE','code':getattr(e,'code',type(e).__name__)})
                        if args.once:raise SystemExit(1)
                    if args.once:return
                    await asyncio.sleep(5)
            asyncio.run(loop())
        elif args.command=='backup':
            from .backup import create_backup
            output(create_backup(settings.database_url,settings.data_dir/'objects',args.file))
        elif args.command=='verify-backup':
            from .backup import verify_backup
            output(verify_backup(args.file))
        elif args.command=='restore-backup':
            from .backup import restore_backup
            output(restore_backup(args.file,args.target))
        elif args.command=='migrate-sqlite-backup':
            from .deployment import migrate_sqlite_backup
            if settings.mode!='production' or not settings.database_url.startswith('postgresql'):
                raise Problem('正式迁移必须在DEEPAHA_MODE=production并指向PostgreSQL空库',409,'MIGRATION_PRODUCTION_REQUIRED')
            result=migrate_sqlite_backup(args.file,settings.database_url,settings.data_dir/'objects')
            if args.report:
                args.report.parent.mkdir(parents=True,exist_ok=True)
                args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            output(result)
        elif args.command=='deploy-check':
            from .deployment import deployment_check
            result=deployment_check(settings)
            output(result)
            if result['status']!='PASS':return 1
        elif args.command=='legacy-inventory':
            from .legacy import inventory
            v=inventory(p.db.engine)
            if args.output:args.output.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
            output(v)
        elif args.command=='legacy-export':
            from .legacy import export_task
            from deepaha.artifacts.local_file import LocalFileObjectStore
            export_task(p.db.engine,LocalFileObjectStore(root=args.object_root,bucket=args.bucket),args.task_id,args.output)
            output({'exported':str(args.output),'database_modified':False,'automatically_approved':False})
    except Problem as e:
        print(f'{e.code}: {e.message}',file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
