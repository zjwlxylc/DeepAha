"""Reviewed, root-only experience release operations. No real WMA calls.
prepare ZIP SHA256 BUILD; pg-test BUILD; deploy BUILD ENV EXPECTED_OLD
ENV is staging-isolated or staging (the latter is the public site).
A failed switch restores old API only; old workers stay stopped after new schema.
"""
import hashlib,importlib.util,io,json,os,re,secrets,shutil,subprocess,sys,time,zipfile,tarfile
from pathlib import Path
BASE=Path('/opt/deepaha')
RUNTIME=BASE/'product-runtimes/experience-v1'
def run(args,**kw):return subprocess.run([str(x) for x in args],check=True,capture_output=True,**kw)
def cfg(env):
 root=(BASE/'staging-current').resolve()
 spec=importlib.util.spec_from_file_location('envtool',root/'ops/sg8a/envtool.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 return m.load('/etc/deepaha/'+env+'.env')
def root_for(build):
 if not re.fullmatch(r'experience-[a-zA-Z0-9-]{1,60}',build):raise RuntimeError('Invalid build')
 return BASE/'releases'/build
def switch(pointer,target):
 pending=pointer.with_name(pointer.name+'.experience-next')
 if pending.exists() or pending.is_symlink():raise RuntimeError('Pending pointer exists')
 pending.symlink_to(target);os.replace(pending,pointer)
def prepare(package,digest,build):
 package=Path(package);dest=root_for(build)
 if hashlib.sha256(package.read_bytes()).hexdigest()!=digest:raise RuntimeError('Package hash mismatch')
 if dest.exists():raise RuntimeError('Release already exists')
 configs=[cfg(x) for x in ['staging','staging-isolated']]
 needles=[v.encode() for c in configs for k,v in c.items() if k in ('DEEPAHA_WMA_API_KEY','DEEPAHA_WMA_AGENT_ID') and len(v)>=8]
 def scan(data,depth=0):
  if any(n in data for n in needles):raise RuntimeError('Host secret found in package')
  if data[:4]==b'PK\x03\x04':
   if depth>8:raise RuntimeError('Nested archive depth exceeded')
   with zipfile.ZipFile(io.BytesIO(data)) as z:
    for f in z.infolist():
     if not f.is_dir():scan(z.read(f),depth+1)
 scan(package.read_bytes())
 with zipfile.ZipFile(package) as z:
  for f in z.infolist():
   p=Path(f.filename)
   if p.is_absolute() or '..' in p.parts or '\\' in f.filename:raise RuntimeError('Unsafe path')
  dest.mkdir();z.extractall(dest)
  for f in z.infolist():
   p=dest/f.filename
   if p.is_file():p.chmod(0o755 if (f.external_attr>>16)&0o111 else 0o644)
 manifest=json.loads((dest/'EXPERIENCE_BUILD.json').read_text())
 for name,h in manifest['files'].items():
  if hashlib.sha256((dest/name).read_bytes()).hexdigest()!=h:raise RuntimeError('Extracted hash mismatch')
 if not RUNTIME.exists():
  # New interpreter prefix and dependencies, leaving the running runtime untouched.
  run([BASE/'product-runtimes/sg8a-v1/bin/python','-m','venv',RUNTIME])
  old=next((BASE/'product-runtimes/sg8a-v1/lib').glob('python*/site-packages'))
  new=next((RUNTIME/'lib').glob('python*/site-packages'))
  shutil.copytree(old,new,dirs_exist_ok=True)
 run([RUNTIME/'bin/python','-m','pip','install','pypdf==6.19.0'])
 (dest/'.venv-product').symlink_to(RUNTIME)
 run([RUNTIME/'bin/python','-m','compileall','-q',dest/'backend/src'])
 print(json.dumps({'prepared':str(dest),'source_commit':manifest['source_commit'],'verified_files':len(manifest['files']),'exact_secret_matches':0}))
def pg_test(build):
 dest=root_for(build);name='deepaha_experience_test_'+secrets.token_hex(6)
 run(['runuser','-u','postgres','--','createdb','--template=template0',name])
 env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPAHA_','WMA_'))}
 env.update(PYTHONPATH=str(dest/'backend/src'),DEEPAHA_EXPERIENCE_TEST_POSTGRES_URL='postgresql+psycopg:///'+name)
 try:
  result=run(['runuser','-u','postgres','--',RUNTIME/'bin/python','-m','pytest','backend/tests/product/test_experience_postgres.py','-q','--tb=short','-p','no:cacheprovider'],cwd=dest,env=env)
  print(result.stdout.decode())
 finally:run(['runuser','-u','postgres','--','dropdb',name])
def deploy(build,env,expected_old):
 if env not in ('staging','staging-isolated'):raise RuntimeError('Invalid environment')
 dest=root_for(build);pointer=BASE/(env+'-current');old=pointer.resolve()
 if str(old)!=expected_old:raise RuntimeError('Current release changed')
 public_before=(BASE/'staging-current').resolve()
 c=cfg(env);other=cfg('staging' if env=='staging-isolated' else 'staging-isolated')
 if c['DEEPAHA_DATABASE_URL']==other['DEEPAHA_DATABASE_URL'] or c['DEEPAHA_DATA_DIR']==other['DEEPAHA_DATA_DIR']:raise RuntimeError('Isolation failed')
 if env=='staging':
  stage_receipt=Path('/var/backups/deepaha/experience')/build/'staging-isolated/receipt.json'
  if json.loads(stage_receipt.read_text()).get('status')!='PASS':raise RuntimeError('Staging gate missing')
 sys.path.insert(0,str(dest/'backend/src'))
 from deepaha.product.service import Product
 from deepaha.product.upgrade import upgrade_experience
 from sqlalchemy import inspect,text
 p=Product(c['DEEPAHA_DATABASE_URL'],Path(c['DEEPAHA_DATA_DIR'])/'objects')
 def busy():
  with p.db.engine.connect() as conn:return conn.execute(text("SELECT count(*) FROM product_tasks WHERE status IN ('RUNNING','QUEUED','RECOVERY_QUEUED')")).scalar()
 if busy():raise RuntimeError('Unfinished tasks; stop without disrupting work')
 backup=Path('/var/backups/deepaha/experience')/build/env;backup.mkdir(parents=True,mode=0o700,exist_ok=False)
 api='deepaha-api@'+env;worker='deepaha-worker@'+env
 active={s:subprocess.run(['systemctl','is-active','--quiet',s]).returncode==0 for s in [api,worker]}
 enabled={s:run(['systemctl','show',s,'-p','UnitFileState','--value']).stdout.decode().strip() for s in [api,worker]}
 receipt={'build':build,'environment':env,'old_release':str(old),'release':str(dest),'source_commit':json.loads((dest/'EXPERIENCE_BUILD.json').read_text())['source_commit'],'wma_validation_called':False,'backup':str(backup),'status':'IN_PROGRESS'}
 migrated=False;success=False
 try:
  run(['systemctl','stop',worker]);run(['systemctl','stop',api])
  if pointer.resolve()!=old or busy():raise RuntimeError('State changed while stopping')
  # Hash every preexisting row, not just counts. Secrets remain only in memory.
  def hashes(names):
   result={}
   with p.db.engine.connect() as conn:
    for name in names:
     rows=conn.execute(text('SELECT * FROM "'+name+'"')).mappings()
     values=sorted(json.dumps(dict(r),sort_keys=True,default=str) for r in rows)
     if name=='product_meta':values=[v for v in values if json.loads(v).get('key')!='experience_schema_version']
     result[name]=hashlib.sha256('\n'.join(values).encode()).hexdigest()
   return result
  names=inspect(p.db.engine).get_table_names();before=hashes(names)
  receipt['migration']=upgrade_experience(p,backup/'pre-upgrade');migrated=True
  if hashes(names)!=before:raise RuntimeError('Existing row content changed during upgrade')
  receipt['existing_rows_unchanged']=True
  archive_path=backup/'pre-upgrade/objects.tar.gz'
  with tarfile.open(archive_path,'r:gz') as archive:
   restored_objects=0
   for member in archive.getmembers():
    if not member.isfile():continue
    relative=Path(member.name).relative_to('objects')
    if '..' in relative.parts:raise RuntimeError('Unsafe object archive path')
    original=p.object_root/relative
    if hashlib.sha256(archive.extractfile(member).read()).digest()!=hashlib.sha256(original.read_bytes()).digest():raise RuntimeError('Object roundtrip mismatch')
    restored_objects+=1
  receipt['objects_archive_roundtrip']={'status':'PASS','files':restored_objects}
  dump=backup/'pre-upgrade/database.dump'
  if dump.exists():
   drill='deepaha_experience_test_restore_'+secrets.token_hex(5)
   run(['runuser','-u','postgres','--','createdb','--template=template0',drill])
   try:
    with dump.open('rb') as f:run(['runuser','-u','postgres','--','pg_restore','--exit-on-error','--no-owner','--no-privileges','-d',drill],stdin=f)
    for table,digest in before.items():
     # SQL JSON canonicalization differs from Python. Verify every table count in restored DB.
     actual=int(run(['runuser','-u','postgres','--','psql','-d',drill,'-Atc','SELECT count(*) FROM "'+table+'"']).stdout)
     with p.db.engine.connect() as conn:
      expected=conn.execute(text('SELECT count(*) FROM "'+table+'"'+(" WHERE key <> 'experience_schema_version'" if table=='product_meta' else ''))).scalar()
     if actual!=expected:raise RuntimeError('Restore row count mismatch: '+table)
    receipt['restore_drill']='PASS'
   finally:run(['runuser','-u','postgres','--','dropdb',drill])
  else:raise RuntimeError('Expected first-upgrade backup absent')
  if pointer.resolve()!=old:raise RuntimeError('Concurrent pointer change')
  switch(pointer,dest)
  # Isolated units use a fixed old runtime; override only interpreter, preserving all sandbox rules.
  if env=='staging-isolated':
   for unit,command in [(api,'serve --host 127.0.0.1 --port ${DEEPAHA_PORT}'),(worker,'worker --isolated-fixture-mode')]:
    directory=Path('/etc/systemd/system')/(unit+'.service.d');directory.mkdir(exist_ok=True)
    (directory/'experience-runtime.conf').write_text('[Service]\nExecStart=\nExecStart=/opt/deepaha/staging-isolated-current/.venv-product/bin/python -m deepaha.product.cli '+command+'\n')
   run(['systemctl','daemon-reload'])
  run(['systemctl','start',api]);run(['systemctl','start',worker])
  import httpx
  origin='http://127.0.0.1:'+str(c['DEEPAHA_PORT'])
  with httpx.Client(base_url=origin,trust_env=False,timeout=10) as client:
   for attempt in range(40):
    try:
     if client.get('/health/ready').status_code==200:break
    except httpx.HTTPError:pass
    time.sleep(1)
   else:raise RuntimeError('Readiness failed')
   checks={path:client.get(path).status_code for path in ['/health/live','/health/ready','/','/product/home.js','/product/profile-editor.js','/product/experience.css','/api/manage/task-search']}
   if any(v!=(401 if path.startswith('/api/') else 200) for path,v in checks.items()):raise RuntimeError('HTTP smoke failed')
   receipt['http_checks']=checks
  time.sleep(15)
  for unit in [api,worker]:
   run(['systemctl','is-active','--quiet',unit])
   if int(run(['systemctl','show',unit,'-p','NRestarts','--value']).stdout)!=0:raise RuntimeError('Service restarted unexpectedly')
  if env=='staging-isolated' and (BASE/'staging-current').resolve()!=public_before:raise RuntimeError('Production pointer changed')
  receipt['functional_smoke']=functional_smoke(p,env)
  receipt['service_check']='PASS';success=True;receipt['status']='PASS'
 finally:
  if not success:
   run(['systemctl','stop',worker]);run(['systemctl','stop',api])
   if pointer.resolve()==dest:switch(pointer,old)
   if active[api]:run(['systemctl','start',api])
   if active[worker] and not migrated:run(['systemctl','start',worker])
   receipt['status']='FAILED';receipt['old_worker_kept_stopped']=migrated
  elif env=='staging-isolated':
   run(['systemctl','stop',worker]);run(['systemctl','stop',api])
   receipt['returned_to_manual_stopped']=True
  receipt['enabled_states']={s:run(['systemctl','show',s,'-p','UnitFileState','--value']).stdout.decode().strip() for s in [api,worker]}
  if receipt['enabled_states']!=enabled:raise RuntimeError('Enablement changed')
  (backup/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
def functional_smoke(p,env):
    """Synthetic HTTPS account checks; never approves content or calls WMA."""
    import httpx
    from sqlalchemy import select
    from deepaha.product.models import Account
    origin='https://www.deepaha.com' if env=='staging' else 'http://127.0.0.1:8200'
    web_origin='https://www.deepaha.com' if env=='staging' else 'https://staging.deepaha.com'
    def attach(client,response):
        if env=='staging-isolated':client.headers['Cookie']='; '.join(k+'='+v for k,v in response.cookies.items())
        client.headers['X-CSRF-Token']=response.json()['csrf']
    name='smoke_release_'+secrets.token_hex(5)
    password=secrets.token_urlsafe(24);invite_id=None;user_name=name+'_user'
    p.create_account(name,password,['operator'])
    try:
        with httpx.Client(base_url=origin,headers={'Origin':web_origin,'Host':web_origin.split('//')[1]},timeout=20) as c:
            for path in ('/','/login','/register','/product/access-ui.js','/product/access.css','/product/birth-date.js'):
                if c.get(path).status_code!=200:raise RuntimeError('Public route failed: '+path)
            r=c.post('/api/auth/login',json={'username':name,'password':password})
            if r.status_code!=200:raise RuntimeError('Public login failed')
            attach(c,r)
            if c.get('/api/review').status_code!=200 or c.get('/api/admin/users').status_code!=200:raise RuntimeError('Maintainer permissions failed')
            r=c.post('/api/admin/invitations',json={'label':'[SMOKE] release engineering verification','max_uses':1})
            if r.status_code!=200:raise RuntimeError('Invitation generation failed')
            item=r.json()['items'][0];invite_id=item['id']
            if len(item['code'])!=4 or not item['code'].isdigit():raise RuntimeError('Invitation format failed')
            with httpx.Client(base_url=origin,headers={'Origin':web_origin,'Host':web_origin.split('//')[1]},timeout=20) as u:
                r=u.post('/api/auth/register',json={'username':user_name,'password':'1234','invite_code':item['code'],'accepted':True})
                if r.status_code!=200:raise RuntimeError('Invited registration failed')
                attach(u,r)
                if u.get('/api/admin/users').status_code!=403:raise RuntimeError('User boundary failed')
                attach(u,r)
                for value in ('2000-02-29',''):
                    if u.put('/api/me/profile',json={'birth_date':value}).status_code!=200:raise RuntimeError('Birth date save failed')
                    if u.get('/api/me/profile').json()['birth_date']!=value:raise RuntimeError('Birth date readback failed')
                state=u.get('/api/me/profile-state').json()
                payload={'expected_version':state['version'],'changes':{'major':'Synthetic release smoke'}}
                if u.patch('/api/me/profile',json=payload).status_code!=200:raise RuntimeError('Profile PATCH failed')
                if u.patch('/api/me/profile',json=payload).status_code!=409:raise RuntimeError('Profile conflict guard failed')
                if u.get('/api/manage/task-search').status_code!=403:raise RuntimeError('Task management boundary failed')
            if c.get('/api/manage/task-search').status_code!=200 or c.get('/api/manage/source-search').status_code!=200:raise RuntimeError('Management search failed')
            with httpx.Client(timeout=20,follow_redirects=False) as edge:
                r=edge.get('https://deepaha.com/register?release_check=1')
                if r.status_code!=301 or r.headers.get('location')!='https://www.deepaha.com/register?release_check=1':raise RuntimeError('Apex redirect failed')
                if edge.get('https://staging.deepaha.com/register').status_code!=401:raise RuntimeError('Staging Basic Auth changed')
    finally:
        if invite_id:p.revoke_invitation(invite_id,actor=name)
        with p.db.tx(False) as s:exists=s.scalar(select(Account.id).where(Account.username==user_name))
        if exists:p.revoke_account(user_name)
        p.revoke_account(name)
    return {'login':'PASS','transport':'HTTPS' if env=='staging' else 'loopback HTTP with explicit secure-cookie forwarding','profile_patch_conflict':'PASS','maintainer_permissions':'PASS','four_digit_invite_four_character_registration':'PASS','ordinary_user_boundary':'PASS','birth_date_save_clear':'PASS','apex_redirect':'PASS','staging_basic_auth':'PASS','synthetic_accounts_disabled':True,'synthetic_invite_revoked':True}


if __name__=='__main__':
 if os.geteuid()!=0:raise SystemExit('Root required')
 action=sys.argv[1]
 {'prepare':prepare,'pg-test':pg_test,'deploy':deploy}[action](*sys.argv[2:])
