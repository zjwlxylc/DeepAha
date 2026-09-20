from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select

from .test_contract import svc
from deepaha.product.errors import Problem
from deepaha.product.models import Account, now


@pytest.fixture
def access(svc):
    svc.create_account('admin', 'long-password-123', ['user', 'operator'])
    return svc


def invite(p, **kw):
    return p.create_invitations(actor='admin', label='九月体验', **kw)['items'][0]


def register(p, code, name='newreader'):
    return p.register_invited(name, 'long-password-123', code, accepted=True, ip=name)


def test_invitation_atomic_capacity_and_secret_redaction(access):
    i=invite(access)
    def attempt(n):
        try: return register(access,i['code'],f'person{n}')
        except Problem as ex: return ex.code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(attempt,[1,2]))
    assert sum(isinstance(r,dict) for r in results)==1
    rows=access.list_invitations(actor='admin')['items']
    assert rows[0]['used_count']==1 and rows[0]['status']=='EXHAUSTED'
    assert all('code' not in row and 'code_hash' not in row for row in rows)
    assert all(i['code'] not in row['summary'] for row in access.access_audit(actor='admin')['items'])


def test_invalid_expired_revoked_duplicate_and_consent(access):
    from deepaha.product.models import Invitation
    i=invite(access)
    with pytest.raises(Problem):access.register_invited('newreader','long-password-123',i['code'],accepted=False)
    with pytest.raises(Problem):register(access,i['code'],'reader')
    assert access.list_invitations(actor='admin')['items'][0]['used_count']==0
    access.revoke_invitation(i['id'],actor='admin')
    with pytest.raises(Problem):register(access,i['code'])
    j=invite(access)
    with access.db.tx() as s:s.get(Invitation,j['id']).expires_at=now()-timedelta(seconds=1)
    with pytest.raises(Problem):register(access,j['code'])
    with pytest.raises(Problem):register(access,'invalid')


def test_roles_account_status_and_last_admin(access):
    with pytest.raises(Problem):access.create_invitations(actor='reviewer',label='no')
    with pytest.raises(Problem):access.list_accounts(actor='reader')
    with access.db.tx(False) as s: aid=s.scalar(select(Account.id).where(Account.username=='admin'))
    with pytest.raises(Problem):access.update_account(aid,actor='admin',active=False,roles=['user'],reason='test')
    access.create_account('admin2','long-password-123',['operator'])
    access.update_account(aid,actor='admin2',active=False,roles=['user'],reason='授权收回')
    session=access.login('reader','long-password-123')
    with access.db.tx(False) as s:rid=s.scalar(select(Account.id).where(Account.username=='reader'))
    access.update_account(rid,actor='admin2',active=False,roles=['user'],reason='测试结束')
    with pytest.raises(Problem):access.authenticate(session['token'])
    access.update_account(rid,actor='admin2',active=True,roles=['user'],reason='重新开放')
    with pytest.raises(Problem):access.authenticate(session['token'])


def test_reset_single_use_and_change_password_revoke_sessions(access):
    with access.db.tx(False) as s:rid=s.scalar(select(Account.id).where(Account.username=='reader'))
    old=access.login('reader','long-password-123')
    first=access.issue_password_reset(rid,actor='admin',reason='身份已核验')
    second=access.issue_password_reset(rid,actor='admin',reason='重新签发')
    with pytest.raises(Problem):access.reset_password(first['code'],'new-password-123')
    access.reset_password(second['code'],'new-password-123')
    with pytest.raises(Problem):access.reset_password(second['code'],'another-password')
    with pytest.raises(Problem):access.authenticate(old['token'])
    new=access.login('reader','new-password-123')
    access.change_password('new-password-123','next-password-123',actor='reader')
    with pytest.raises(Problem):access.authenticate(new['token'])
    assert access.login('reader','next-password-123')['roles']==['user']


def test_api_invite_only_csrf_roles_and_strict_registration(access,tmp_path):
    from fastapi.testclient import TestClient
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    settings=Settings(data_dir=tmp_path,database_url=access.database_url,allow_registration=True)
    with TestClient(create_app(settings,access)) as c:
        assert c.get('/api/site').json()['registration_mode']=='invite'
        assert c.post('/api/auth/register',json={'username':'visitor','password':'long-password-123'}).status_code==422
        assert c.get('/api/admin/users').status_code==401
        auth=c.post('/api/auth/login',json={'username':'admin','password':'long-password-123'}).json()
        assert c.post('/api/admin/invitations',json={'label':'test'}).status_code==403
        r=c.post('/api/admin/invitations',json={'label':'test'},headers={'X-CSRF-Token':auth['csrf']})
        assert r.status_code==200
        code=r.json()['items'][0]['code']
        c.cookies.clear()
        data={'username':'visitor','password':'long-password-123','invite_code':code,'accepted':True}
        assert c.post('/api/auth/register',json={**data,'roles':['admin']}).status_code==422
        assert c.post('/api/auth/register',json=data).status_code==200
        assert c.get('/api/admin/users').status_code==403
        assert c.get('/api/auth/me').json()['roles']==['user']


def test_registration_limit_is_persistent_across_failures(access):
    for _ in range(20):
        with pytest.raises(Problem) as ex:access.register_invited('visitor','long-password-123','invalid',accepted=True,ip='same-ip')
        assert ex.value.status==400
    with pytest.raises(Problem) as ex:access.register_invited('visitor','long-password-123',invite(access)['code'],accepted=True,ip='same-ip')
    assert ex.value.status==429


def test_expired_reset_and_disabled_user_cannot_reset(access):
    from deepaha.product.models import PasswordReset
    from deepaha.product.auth import digest
    with access.db.tx(False) as s:rid=s.scalar(select(Account.id).where(Account.username=='reader'))
    token=access.issue_password_reset(rid,actor='admin',reason='verified')['code']
    with access.db.tx() as s:s.get(PasswordReset,digest(token)).expires_at=now()-timedelta(seconds=1)
    with pytest.raises(Problem):access.reset_password(token,'new-password-123')
    token=access.issue_password_reset(rid,actor='admin',reason='verified')['code']
    access.update_account(rid,actor='admin',active=False,roles=['user'],reason='disabled')
    with pytest.raises(Problem):access.reset_password(token,'new-password-123')


def test_closed_registration_and_cross_origin_admin_write(access,tmp_path):
    from fastapi.testclient import TestClient
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    with TestClient(create_app(Settings(data_dir=tmp_path,database_url=access.database_url),access)) as c:
        assert c.post('/api/auth/register',json={'username':'visitor','password':'long-password-123','invite_code':invite(access)['code'],'accepted':True}).status_code==403
        auth=c.post('/api/auth/login',json={'username':'admin','password':'long-password-123'}).json()
        assert c.post('/api/admin/invitations',json={'label':'test'},headers={'X-CSRF-Token':auth['csrf'],'Origin':'https://untrusted.example'}).status_code==403


def test_explicit_additive_upgrade_preserves_accounts_and_is_repeatable(access):
    from sqlalchemy import inspect
    from deepaha.product.models import Base,ACCESS_TABLE_NAMES
    with access.db.tx(False) as s:before={a.id:a.password_hash for a in s.scalars(select(Account))}
    tables=[t for t in Base.metadata.sorted_tables if t.name in ACCESS_TABLE_NAMES]
    Base.metadata.drop_all(access.db.engine,tables=list(reversed(tables)))
    assert not ACCESS_TABLE_NAMES.intersection(inspect(access.db.engine).get_table_names())
    for _ in range(2):Base.metadata.create_all(access.db.engine,tables=tables)
    with access.db.tx(False) as s:assert before=={a.id:a.password_hash for a in s.scalars(select(Account))}


def test_isolated_worker_cli_preserves_no_remote_and_no_schedules(svc,tmp_path,monkeypatch):
    from deepaha.product import cli,worker
    from deepaha.product.config import Settings,ConnectionConfig
    monkeypatch.setattr(Settings,'from_env',lambda:Settings(data_dir=tmp_path,database_url=svc.database_url))
    def forbidden(*args,**kw):raise AssertionError('Isolated fixture worker must not schedule or load remote credentials')
    monkeypatch.setattr(worker,'schedule_weekly_digests',forbidden)
    monkeypatch.setattr(worker,'schedule_due',forbidden)
    monkeypatch.setattr(ConnectionConfig,'factory',forbidden)
    async def idle(p,*,client_factory):
        assert client_factory is None
        return {'state':'NOT_CONFIGURED'}
    monkeypatch.setattr(worker,'run_once',idle)
    assert cli.main(['worker','--isolated-fixture-mode','--once']) in (None,0)


def test_preserved_empty_bootstrap_rejects_existing_database(svc,tmp_path):
    from deepaha.product.empty_bootstrap import bootstrap_empty
    with pytest.raises(RuntimeError,match='NONEMPTY_SCHEMA'):bootstrap_empty(svc.database_url,tmp_path/'objects')


def test_host_account_and_password_maintenance_revoke_unused_reset_codes(access,tmp_path,monkeypatch):
    from deepaha.product import cli
    from deepaha.product.config import Settings
    with access.db.tx(False) as s:rid=s.scalar(select(Account.id).where(Account.username=='reader'))
    code=access.issue_password_reset(rid,actor='admin',reason='verified')['code']
    access.revoke_account('reader');access.revoke_account('reader',active=True)
    with pytest.raises(Problem):access.reset_password(code,'New-password-123')

    code=access.issue_password_reset(rid,actor='admin',reason='verified')['code']
    monkeypatch.setattr(Settings,'from_env',lambda:Settings(data_dir=tmp_path,database_url=access.database_url))
    monkeypatch.setattr(cli.getpass,'getpass',lambda prompt:'CLI-new-password-123')
    assert cli.main(['password-reset','reader']) in (None,0)
    with pytest.raises(Problem):access.reset_password(code,'New-password-123')


def test_four_character_passwords_across_account_and_recovery_flows(access):
    from deepaha.product.auth import password_hash,verify_password
    assert verify_password('1234',password_hash('1234'))
    with pytest.raises(Problem):password_hash('123')
    with pytest.raises(Problem):password_hash('a'*257)
    i=invite(access)
    r=access.register_invited('shortpass','1234',i['code'],accepted=True)
    assert access.login('shortpass','1234')['username']=='shortpass'
    access.change_password('1234','abcd',actor='shortpass')
    reset=access.issue_password_reset(r['id'],actor='operator',reason='identity checked')
    access.reset_password(reset['code'],'5678')
    assert access.login('shortpass','5678')['roles']==['user']


def test_four_digit_codes_unique_and_never_reissued(access,monkeypatch):
    from deepaha.product import access as module
    monkeypatch.setattr(module,'INVITATION_CODE_SPACE',3)
    first=access.create_invitations(actor='operator',label='batch',count=2)['items']
    assert len({r['code'] for r in first})==2
    assert all(len(r['code'])==4 and r['code'].isdigit() for r in first)
    for r in first:access.revoke_invitation(r['id'],actor='operator')
    last=access.create_invitations(actor='operator',label='next')['items'][0]
    assert last['code'] not in {r['code'] for r in first}
    with pytest.raises(Problem) as ex:access.create_invitations(actor='operator',label='full')
    assert ex.value.code=='INVITE_CODES_EXHAUSTED'


def test_legacy_admin_migration_preserves_password_and_roles_is_idempotent(access):
    # Simulate the previously deployed schema/account without using the new role API.
    with access.db.tx() as s:
        a=s.scalar(select(Account).where(Account.username=='admin'))
        a.roles=['user','reviewer','admin'];old_hash=a.password_hash
    old_session=access.login('admin','long-password-123')
    result=access.migrate_access_roles()
    assert result['migrated_accounts']==1
    with access.db.tx(False) as s:
        a=s.scalar(select(Account).where(Account.username=='admin'))
        assert set(a.roles)=={'user','reviewer','operator'} and a.password_hash==old_hash
    with pytest.raises(Problem):access.authenticate(old_session['token'])
    assert access.migrate_access_roles()['migrated_accounts']==0
    assert access.create_invitations(actor='admin',label='works')['items']
    with pytest.raises(Problem):access.create_account('obsolete','1234',['admin'])
    assert access.restore_access_roles(result['changes'])['restored_accounts']==1
    with access.db.tx(False) as s:
        a=s.scalar(select(Account).where(Account.username=='admin'))
        assert a.roles==['user','reviewer','admin'] and a.password_hash==old_hash


def test_api_four_character_password_and_operator_management(access,tmp_path):
    from fastapi.testclient import TestClient
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    with TestClient(create_app(Settings(data_dir=tmp_path,database_url=access.database_url,allow_registration=True),access)) as c:
        auth=c.post('/api/auth/login',json={'username':'operator','password':'long-password-123'}).json()
        headers={'X-CSRF-Token':auth['csrf']}
        r=c.post('/api/admin/invitations',json={'label':'operator invite'},headers=headers)
        assert r.status_code==200
        code=r.json()['items'][0]['code'];assert len(code)==4 and code.isdigit()
        assert c.get('/api/admin/users').status_code==200
        c.cookies.clear()
        payload={'username':'api_short','password':'123','invite_code':code,'accepted':True}
        assert c.post('/api/auth/register',json=payload).status_code==422
        assert c.post('/api/auth/register',json={**payload,'password':'1234'}).status_code==200
        assert c.get('/api/admin/users').status_code==403


def test_operator_inherits_reviewer_permissions_api(access,tmp_path):
    from .test_contract import packet
    from fastapi.testclient import TestClient
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    preview=access.ingest(access.test_source,packet(),actor='operator')
    with TestClient(create_app(Settings(data_dir=tmp_path,database_url=access.database_url),access)) as c:
        auth=c.post('/api/auth/login',json={'username':'operator','password':'long-password-123'}).json()
        assert auth['roles']==['operator']
        assert c.get('/api/review').status_code==200
        r=c.post('/api/review/'+preview['id']+'/decision',json={'decision':'APPROVE','preview_hash':preview['preview_hash'],'note':'','request_key':'operator-inherits-review'},headers={'X-CSRF-Token':auth['csrf']})
        assert r.status_code==200 and r.json()['decision']=='APPROVE'
        c.post('/api/auth/login',json={'username':'reviewer','password':'long-password-123'})
        assert c.get('/api/admin/users').status_code==403
