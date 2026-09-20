"""Root-only public Beta release switch after explicit staging acceptance. Run from a reviewed local artifact.

Usage: python deploy_staging.py PACKAGE SHA256 EXPECTED_OLD_RELEASE BUILD_ID
Publishes www via its existing staging/8100 services; no Nginx, Ops Gateway or WMA configuration changes.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

CURRENT=Path('/opt/deepaha/staging-current')
ENV=Path('/etc/deepaha/staging.env')
RUNTIME=Path('/opt/deepaha/product-runtimes/sg8a-v1/bin/python')
API='deepaha-api@staging'
WORKER='deepaha-worker@staging'

def run(args,**kwargs):
    return subprocess.run(args,check=True,capture_output=True,**kwargs)

def load_env(path,root):
    spec=importlib.util.spec_from_file_location('access_envtool',root/'ops/sg8a/envtool.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.load(path)

def switch(target):
    temp=CURRENT.with_name(CURRENT.name+'.access-next')
    if temp.exists() or temp.is_symlink():raise RuntimeError('Unexpected pending release pointer')
    temp.symlink_to(target);os.replace(temp,CURRENT)

def main():
    if os.geteuid()!=0:raise RuntimeError('Requires root')
    package=Path(sys.argv[1]);expected_hash,expected_old,build=sys.argv[2:5]
    import re
    if not re.fullmatch(r'beta-access-[a-zA-Z0-9-]{1,80}',build):raise RuntimeError('Invalid build')
    if str(CURRENT.resolve())!=expected_old:raise RuntimeError('Staging changed; stop')
    if hashlib.sha256(package.read_bytes()).hexdigest()!=expected_hash:raise RuntimeError('Package SHA mismatch')
    old=CURRENT.resolve();live=Path('/opt/deepaha/staging-isolated-current').resolve()
    cfg=load_env(ENV,old);public=load_env('/etc/deepaha/staging-isolated.env',old)
    if cfg['DEEPAHA_DATABASE_URL']==public['DEEPAHA_DATABASE_URL'] or cfg['DEEPAHA_DATA_DIR']==public['DEEPAHA_DATA_DIR']:raise RuntimeError('Staging is not isolated')
    dest=Path('/opt/deepaha/releases')/build
    if dest.exists():raise RuntimeError('Release already exists; do not overwrite')
    backup=Path('/var/backups/deepaha/public-beta')/build
    backup.mkdir(parents=True,mode=0o700,exist_ok=False);os.chmod(backup,0o700)
    receipt={'build':build,'old_release':str(old),'new_release':str(dest),'backup':str(backup),'www_modified':True,'isolated_staging_modified':False,'wma_called':False}
    # Compare exact host-injected secrets in every nested ZIP without exporting values.
    needles=[v.encode() for e in (cfg,public) for k,v in e.items() if k in ('DEEPAHA_WMA_API_KEY','DEEPAHA_WMA_AGENT_ID') and len(v)>=8]
    def scan(data,depth=0):
        if any(n in data for n in needles):raise RuntimeError('Exact credential match in package')
        if data[:4]==b'PK\x03\x04':
            if depth>8:raise RuntimeError('Nested archive limit exceeded')
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    if not info.is_dir():scan(z.read(info),depth+1)
    scan(package.read_bytes());receipt['exact_wma_secret_matches']=0;receipt['credential_values_compared']=len(needles)
    with zipfile.ZipFile(package) as z:
        for item in z.infolist():
            path=Path(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename:raise RuntimeError('Unsafe package path')
        dest.mkdir();z.extractall(dest)
        for item in z.infolist():
            path=dest/item.filename
            if path.is_file():path.chmod(0o755 if (item.external_attr>>16)&0o111 else 0o644)
    (dest/'.venv-product').symlink_to(RUNTIME.parent.parent)
    manifest=json.loads((dest/'BETA_BUILD.json').read_text())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((dest/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Extracted file mismatch')
    receipt['verified_package_files']=len(manifest['files'])
    run([str(RUNTIME),'-m','compileall','-q',str(dest/'backend/src')])
    candidate_env=os.environ.copy();candidate_env['PYTHONPATH']=str(dest/'backend/src')
    help_output=run([str(RUNTIME),'-m','deepaha.product.cli','worker','--help'],env=candidate_env).stdout
    if b'--isolated-fixture-mode' not in help_output:raise RuntimeError('Missing installed isolated-worker CLI contract')
    sys.path.insert(0,str(dest/'backend/src'))
    from sqlalchemy import create_engine,inspect,text
    from sqlalchemy.engine import make_url
    engine=create_engine(cfg['DEEPAHA_DATABASE_URL'])
    with engine.connect() as c:
        busy=c.execute(text("SELECT count(*) FROM product_tasks WHERE status IN ('RUNNING','QUEUED','RECOVERY_QUEUED')")).scalar()
        if busy:raise RuntimeError('Pending staging investigations; stop before quiescing')
    url=make_url(cfg['DEEPAHA_DATABASE_URL'])
    pg=os.environ.copy();pg.update({'PGHOST':url.host or 'localhost','PGPORT':str(url.port or 5432),'PGUSER':url.username or '', 'PGPASSWORD':url.password or '', 'PGDATABASE':url.database or ''})
    active={name:subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0 for name in (API,WORKER)}
    env_backup=backup/'staging.env';shutil.copy2(ENV,env_backup);env_backup.chmod(0o600)
    changed=False;stopped=False;success=False;role_changes=[];roles_migrated=False
    try:
        if CURRENT.resolve()!=old:raise RuntimeError('Concurrent release detected')
        stopped=True
        run(['systemctl','stop',WORKER]);run(['systemctl','stop',API])
        with engine.connect() as c:
            if c.execute(text("SELECT count(*) FROM product_tasks WHERE status IN ('RUNNING','QUEUED','RECOVERY_QUEUED')")).scalar():raise RuntimeError('Work arrived during quiescing; restore services')
            before={name:c.execute(text('SELECT count(*) FROM "'+name+'"')).scalar() for name in inspect(engine).get_table_names()}
        run(['pg_dump','--format=custom','--file='+str(backup/'database.dump')],env=pg)
        run(['pg_restore','--list',str(backup/'database.dump')])
        with tarfile.open(backup/'objects.tar.gz','w:gz') as tar:
            objects=Path(cfg['DEEPAHA_DATA_DIR'])/'objects'
            if objects.exists():tar.add(objects,arcname='objects')
        # Restore proof uses a new temporary database only, never the staging or live DB.
        drill='deepaha_access_drill_'+secrets.token_hex(6)
        run(['runuser','-u','postgres','--','createdb','--template=template0',drill])
        try:
            with (backup/'database.dump').open('rb') as source:run(['runuser','-u','postgres','--','pg_restore','--exit-on-error','--no-owner','--no-privileges','-d',drill],stdin=source)
            count=int(run(['runuser','-u','postgres','--','psql','-d',drill,'-Atc','SELECT count(*) FROM product_accounts']).stdout)
            if count!=before['product_accounts']:raise RuntimeError('Restore account count mismatch')
        finally:run(['runuser','-u','postgres','--','dropdb',drill])
        receipt['backup_restore_drill']='PASS'
        from deepaha.product.models import Base,ACCESS_TABLE_NAMES
        Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name in ACCESS_TABLE_NAMES])
        with engine.connect() as c:
            after={name:c.execute(text('SELECT count(*) FROM "'+name+'"')).scalar() for name in before}
        if before!=after:raise RuntimeError('Migration changed existing rows')
        receipt['additive_migration_existing_counts_preserved']=True
        from deepaha.product.service import Product
        from deepaha.product.models import Account
        from sqlalchemy import select
        p=Product(cfg['DEEPAHA_DATABASE_URL'],Path(cfg['DEEPAHA_DATA_DIR'])/'objects')
        # Save compensating role changes before migration; passwords are never exported.
        with p.db.tx(False) as s:
            password_hashes={a.id:a.password_hash for a in s.scalars(select(Account))}
            role_changes=[{'id':a.id,'before':a.roles,'after':list(dict.fromkeys([r for r in a.roles if r!='admin']+['operator']))}
                          for a in s.scalars(select(Account)) if 'admin' in a.roles]
        role_backup=backup/'access-roles-rollback.json'
        role_backup.write_text(json.dumps(role_changes));role_backup.chmod(0o600)
        migration=p.migrate_access_roles();roles_migrated=True
        receipt['legacy_admins_migrated_to_operator']=migration['migrated_accounts']
        with p.db.tx(False) as s:
            if password_hashes!={a.id:a.password_hash for a in s.scalars(select(Account))}:raise RuntimeError('Role migration changed account passwords')
            receipt['existing_password_hashes_unchanged']=True
            admins=[a.username for a in s.scalars(select(Account).where(Account.active.is_(True))) if 'operator' in a.roles]
            conflict=s.scalar(select(Account).where(Account.username=='beta_operator'))
        if not admins:raise RuntimeError('No active maintainer; stop publication')
        receipt['existing_operator_retained']=True
        p.db.engine.dispose()
        # Replace only the registration flag; preserve host-owned secrets and file permissions.
        value=ENV.read_text();lines=[line for line in value.splitlines() if not line.startswith('DEEPAHA_ALLOW_REGISTRATION=')]
        changed=True;ENV.write_text('\n'.join(lines+['DEEPAHA_ALLOW_REGISTRATION=1'])+'\n')
        if CURRENT.resolve()!=old:raise RuntimeError('Concurrent release detected before switch')
        switch(dest)
        run(['systemctl','start',API])
        if active[WORKER]:run(['systemctl','start',WORKER])
        import httpx
        with httpx.Client(base_url='http://127.0.0.1:8100',headers={'Host':'www.deepaha.com'},timeout=10) as client:
            for _ in range(30):
                try:
                    response=client.get('/health/ready')
                    if response.status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(1)
            else:raise RuntimeError('Staging failed readiness')
            site=client.get('/api/site').json()
            if site.get('registration_mode')!='invite':raise RuntimeError('Invitation mode not active')
            for path in ('/','/register','/product/access-ui.js','/product/access.css'):
                if client.get(path).status_code!=200:raise RuntimeError('Staging route failed: '+path)
        # A process may briefly be active before argparse/runtime failure. Observe
        # both services across the restart window instead of accepting a transient start.
        observed={}
        for _ in range(3):
            time.sleep(5)
            for unit in (API,WORKER):
                if unit==WORKER and not active[WORKER]:continue
                run(['systemctl','is-active','--quiet',unit])
                count=run(['systemctl','show',unit,'-p','NRestarts','--value']).stdout.strip()
                if unit in observed and count!=observed[unit]:raise RuntimeError('Service restarted during observation: '+unit)
                observed[unit]=count
        receipt['service_stability_observation']='PASS'
        if Path('/opt/deepaha/staging-isolated-current').resolve()!=live:raise RuntimeError('Isolated staging pointer changed externally')
        receipt['functional_smoke']=functional_smoke(p)
        receipt['status']='DEPLOYED_AND_VERIFIED';success=True
    finally:
        if not success and stopped:
            if roles_migrated and role_changes:
                run(['systemctl','stop',API]);run(['systemctl','stop',WORKER])
                p.restore_access_roles(role_changes)
            if CURRENT.resolve()==dest:switch(old)
            if changed:shutil.copy2(env_backup,ENV)
            for name,was_active in active.items():
                if was_active:run(['systemctl','restart',name])
            receipt['status']='ROLLED_BACK_AFTER_FAILURE'
        for path in backup.iterdir():
            if path.is_file():path.chmod(0o600)
        (backup/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        (backup/'receipt.json').chmod(0o600)
        print(json.dumps(receipt,indent=2),flush=True)


def functional_smoke(p):
    """Synthetic HTTPS account checks; never approves content or calls WMA."""
    import httpx
    from sqlalchemy import select
    from deepaha.product.models import Account
    name='smoke_release_'+secrets.token_hex(5)
    password=secrets.token_urlsafe(24);invite_id=None;user_name=name+'_user'
    p.create_account(name,password,['operator'])
    try:
        with httpx.Client(base_url='https://www.deepaha.com',headers={'Origin':'https://www.deepaha.com'},timeout=20) as c:
            for path in ('/','/login','/register','/product/access-ui.js','/product/access.css'):
                if c.get(path).status_code!=200:raise RuntimeError('Public route failed: '+path)
            r=c.post('/api/auth/login',json={'username':name,'password':password})
            if r.status_code!=200:raise RuntimeError('Public login failed')
            c.headers['X-CSRF-Token']=r.json()['csrf']
            if c.get('/api/review').status_code!=200 or c.get('/api/admin/users').status_code!=200:raise RuntimeError('Maintainer permissions failed')
            r=c.post('/api/admin/invitations',json={'label':'[SMOKE] release engineering verification','max_uses':1})
            if r.status_code!=200:raise RuntimeError('Invitation generation failed')
            item=r.json()['items'][0];invite_id=item['id']
            if len(item['code'])!=4 or not item['code'].isdigit():raise RuntimeError('Invitation format failed')
            with httpx.Client(base_url='https://www.deepaha.com',headers={'Origin':'https://www.deepaha.com'},timeout=20) as u:
                r=u.post('/api/auth/register',json={'username':user_name,'password':'1234','invite_code':item['code'],'accepted':True})
                if r.status_code!=200:raise RuntimeError('Invited registration failed')
                if u.get('/api/admin/users').status_code!=403:raise RuntimeError('User boundary failed')
            with httpx.Client(timeout=20,follow_redirects=False) as edge:
                r=edge.get('https://deepaha.com/register?release_check=1')
                if r.status_code!=301 or r.headers.get('location')!='https://www.deepaha.com/register?release_check=1':raise RuntimeError('Apex redirect failed')
                if edge.get('https://staging.deepaha.com/register').status_code!=401:raise RuntimeError('Staging Basic Auth changed')
    finally:
        if invite_id:p.revoke_invitation(invite_id,actor=name)
        with p.db.tx(False) as s:exists=s.scalar(select(Account.id).where(Account.username==user_name))
        if exists:p.revoke_account(user_name)
        p.revoke_account(name)
    return {'https_login':'PASS','maintainer_permissions':'PASS','four_digit_invite_four_character_registration':'PASS','ordinary_user_boundary':'PASS','apex_redirect':'PASS','staging_basic_auth':'PASS','synthetic_accounts_disabled':True,'synthetic_invite_revoked':True}

if __name__=='__main__':main()
