"""Mobile R2: real database actions, tenant isolation, release consistency."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import re
import pytest
from sqlalchemy import select, func
from .test_api import client, login
from .test_contract import svc, packet
from deepaha.product.models import TargetAction, TargetActionEvent, Account, CatalogTarget, Notice, now


def target(p):
    a=p.ingest(p.test_source,packet(),actor='operator')
    p.decide(a['id'],'APPROVE',a['preview_hash'],'','r2-publish',actor='reviewer')
    return p.catalog()['items'][0]['id']


def test_save_is_atomic_idempotent_and_never_resets_progress(svc):
    oid=target(svc)
    assert hasattr(svc,'save_opportunity'), 'Missing idempotent save operation'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:svc.save_opportunity(oid,actor='reader'),range(2)))
    assert sum(r['created'] for r in results)==1
    svc.set_action(oid,'PREPARING',actor='reader',note='已整理作品集')
    with svc.db.tx(False) as s:
        before=s.scalar(select(func.count()).select_from(TargetActionEvent))
    again=svc.save_opportunity(oid,actor='reader')
    assert not again['created'] and again['status']=='PREPARING'
    assert again['note']=='已整理作品集'
    with svc.db.tx(False) as s:assert s.scalar(select(func.count()).select_from(TargetActionEvent))==before
    svc.create_account('other','long-password-123',['user'])
    assert svc.action_state(oid,actor='other')['saved'] is False
    assert svc.action_state(oid,actor='reader')['saved'] is True


def test_save_api_auth_csrf_and_real_state(client,svc):
    oid=target(svc);base='/api/me/actions/'+oid
    assert client.get(base).status_code==401
    login(client,'reader')
    assert client.post(base+'/save',headers={'X-CSRF-Token':'bad'}).status_code==403
    saved=client.post(base+'/save');assert saved.status_code==200,saved.text
    assert client.get(base).json()['status']=='SAVED'
    assert client.post(base+'/save').json()['created'] is False


def test_withdrawn_action_remains_identifiable_and_removable(svc):
    oid=target(svc);svc.set_action(oid,'SAVED',actor='reader')
    previous=svc.my_actions(actor='reader')[0]['opportunity']['title']
    svc.withdraw(oid,'原公告撤回',actor='reviewer')
    assert svc.my_actions(actor='reader')[0]['opportunity']['title']==previous
    assert svc.remove_action(oid,actor='reader')['removed'] is True
    assert not svc.my_actions(actor='reader')
    assert not svc.catalog()['items']


def test_summary_requires_auth_and_has_safe_minimal_fields(client,svc):
    assert client.get('/api/me/summary').status_code==401
    oid=target(svc);svc.set_action(oid,'PREPARING',actor='reader',note='secret note')
    login(client,'reader');r=client.get('/api/me/summary')
    assert r.status_code==200,r.text
    assert r.json()['counts']['PREPARING']==1 and r.json()['action_total']==1
    assert 'secret' not in r.text and 'password' not in r.text


def test_frontend_build_addresses_the_whole_module_graph(client):
    r=client.get('/');assert 'no-store' in r.headers.get('cache-control','')
    html=r.text
    m=re.search(r'src="(/product/_v/[^/]+/)app.js"',html)
    assert m,'Version namespace missing'
    prefix=m.group(1)
    for name in ['app.js','core.js','user.js','home.js','actions-ui.js','profile-editor.js','operations-ui.js','mobile-r2.css']:
        asset=client.get(prefix+name)
        assert asset.status_code==200,(name,asset.text)
        assert 'immutable' in asset.headers['cache-control']
    assert client.get('/product/core.js').headers.get('cache-control')=='no-cache'
    assert client.get('/product/_v/not-this-release/core.js').status_code==404
    site=client.get('/api/site').json();assert site['frontend_build'] in prefix
    assert site['product_iteration']=='mobile-r3'


def test_summary_and_digest_do_not_truncate_more_than_fifty_actions(svc):
    oid=target(svc)
    with svc.db.tx() as s:
        a=svc._account(s,'reader'); t=svc._target_row(s,oid)
        for i in range(65):
            s.add(TargetAction(account_id=a.id,target_public_id='historic-'+str(i),opportunity_id=t.opportunity_id,status='SAVED'))
    from deepaha.product.mobile import summary
    assert summary(svc,'reader')['action_total']==65
    assert len(svc.my_actions(actor='reader'))==50
    assert svc.weekly_digest(actor='reader')['action_summary']['SAVED']==65


def test_asset_manifest_detects_changed_module_before_immutable_serve(tmp_path):
    import importlib
    assert importlib.util.find_spec('deepaha.product.frontend_assets'), 'Release validator missing'
    from deepaha.product.frontend_assets import build_release, validate_release
    root=tmp_path/'static';root.mkdir()
    (root/'index.html').write_text('<script type="module" src="/product/app.js"></script>')
    (root/'app.js').write_text("import './core.js';")
    (root/'core.js').write_text('export const value=1;')
    html,manifest=build_release(root)
    (root/'index.html').write_text(html)
    (root/'asset-release.json').write_text(json.dumps(manifest))
    assert validate_release(root)==manifest['build']
    (root/'core.js').write_text('export const value=2;')
    with pytest.raises(RuntimeError,match='ASSET_BUILD_STALE'):validate_release(root)
