from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select

from .test_contract import svc
from deepaha.product.errors import Problem
from deepaha.product.models import Account, now


@pytest.fixture
def access(svc):
    svc.create_account('admin', 'long-password-123', ['user', 'admin'])
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
    assert i['code'] not in str(rows)
    assert i['code'] not in str(access.access_audit(actor='admin'))


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
    with pytest.raises(Problem):access.create_invitations(actor='operator',label='no')
    with pytest.raises(Problem):access.list_accounts(actor='reader')
    with access.db.tx(False) as s: aid=s.scalar(select(Account.id).where(Account.username=='admin'))
    with pytest.raises(Problem):access.update_account(aid,actor='admin',active=False,roles=['user'],reason='test')
    access.create_account('admin2','long-password-123',['admin'])
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
