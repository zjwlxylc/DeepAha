import io
import json
import zipfile
from copy import deepcopy

import pytest

from .test_contract import svc, packet


def mutate_packet(base: bytes, mutate):
    src = zipfile.ZipFile(io.BytesIO(base))
    files = {name: src.read(name) for name in src.namelist()}
    data = json.loads(files['opportunities.json'])
    mutate(data)
    files['opportunities.json'] = json.dumps(data, ensure_ascii=False).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, value in files.items():
            z.writestr(name, value)
    return out.getvalue()


def two_positions_packet():
    def change(data):
        data['units'] = [{
            'id': 'org-1',
            'name': '海湾研究中心科研部',
            'unit_level': [{'field': '工作地点', 'value': '杭州'}],
            'positions': [
                {'id': 'pos-research', 'name': '工程研究助理', 'code': 'A01', 'facts': [
                    {'field': '学历', 'value': '硕士研究生以上', 'status': 'UNKNOWN', 'evidence': []},
                    {'field': '岗位描述', 'value': '参与工程研究与数据整理。', 'status': 'CONFIRMED', 'evidence': []},
                ]},
                {'id': 'pos-admin', 'name': '技术项目管理员', 'code': 'A02', 'facts': [
                    {'field': '学历', 'value': '本科及以上', 'status': 'UNKNOWN', 'evidence': []},
                    {'field': '岗位描述', 'value': '负责技术项目协调。', 'status': 'CONFIRMED', 'evidence': []},
                ]},
            ],
        }]
    return mutate_packet(packet('城市工程研究院·青年人才引进'), change)


def approve(svc, blob, key='approve-targets'):
    preview = svc.ingest(svc.test_source, blob, actor='operator')
    receipt = svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', key, actor='reviewer')
    return preview, receipt


def test_one_notice_two_positions_becomes_two_catalog_targets(svc):
    _, receipt = approve(svc, two_positions_packet())
    catalog = svc.catalog(limit=50)
    assert catalog['total'] == 2
    assert {x['title'] for x in catalog['items']} == {'工程研究助理', '技术项目管理员'}
    assert all(x['id'].startswith('unit_') for x in catalog['items'])
    assert '城市工程研究院·青年人才引进' not in {x['title'] for x in catalog['items']}
    assert len(receipt['public_ids']) == 1
    assert len(receipt['catalog_target_ids']) == 2


def test_group_is_scope_not_catalog_card(svc):
    approve(svc, two_positions_packet())
    assert '海湾研究中心科研部' not in {x['title'] for x in svc.catalog(limit=50)['items']}
    detail = svc.detail(next(x['id'] for x in svc.catalog(limit=50)['items'] if x['title'] == '工程研究助理'))
    assert detail['parent_announcement']['title'] == '城市工程研究院·青年人才引进'
    assert any(x['value'] == '杭州' for x in detail['ancestor_fields'])


def test_root_only_notice_has_singleton_fallback(svc):
    blob = mutate_packet(packet('青年实践计划'), lambda data: data.update({'units': []}))
    _, receipt = approve(svc, blob)
    catalog = svc.catalog(limit=50)
    assert catalog['total'] == 1
    assert catalog['items'][0]['title'] == '青年实践计划'
    assert catalog['items'][0]['id'].startswith('opp_')
    assert receipt['catalog_target_ids'] == [catalog['items'][0]['id']]


def test_actions_are_independent_per_position(svc):
    approve(svc, two_positions_packet())
    rows = svc.catalog(limit=50)['items']
    a = next(x for x in rows if x['title'] == '工程研究助理')
    b = next(x for x in rows if x['title'] == '技术项目管理员')
    svc.set_action(a['id'], 'SAVED', actor='reader')
    mine = svc.my_actions(actor='reader')
    assert [x['opportunity']['id'] for x in mine] == [a['id']]
    assert b['id'] not in {x['opportunity']['id'] for x in mine}


def test_unit_public_ids_stay_stable_across_root_revisions(svc):
    _, first = approve(svc, two_positions_packet(), 'rev-one')
    before = {x['title']: x['id'] for x in svc.catalog(limit=50)['items']}

    def change(data):
        data['announcement_level'].append({'field': '补充说明', 'value': '第二版公告共同说明', 'status': 'UNKNOWN', 'evidence': []})
    second_blob = mutate_packet(two_positions_packet(), change)
    preview = svc.ingest(svc.test_source, second_blob, actor='operator')
    svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', 'rev-two', actor='reviewer')
    after = {x['title']: x['id'] for x in svc.catalog(limit=50)['items']}
    assert before == after
    assert set(first['catalog_target_ids']) == set(before.values())


def test_hundred_positions_are_paged_as_targets(svc):
    def change(data):
        data['units'] = [{
            'id': 'bulk-org', 'name': '批量岗位单位',
            'positions': [
                {'id': f'position-{i:03d}', 'name': f'岗位{i:03d}', 'code': f'P{i:03d}', 'facts': []}
                for i in range(100)
            ]
        }]
    approve(svc, mutate_packet(packet('百岗招聘公告'), change))
    first = svc.catalog(offset=0, limit=50)
    second = svc.catalog(offset=50, limit=50, read_version=first['read_version'])
    assert first['total'] == 100
    assert len(first['items']) == len(second['items']) == 50
    assert {x['id'] for x in first['items']}.isdisjoint({x['id'] for x in second['items']})


def test_missing_position_in_update_is_not_silently_withdrawn(svc):
    approve(svc, two_positions_packet(), 'initial-two')
    before = {x['title']: x['id'] for x in svc.catalog(limit=50)['items']}

    def remove_one(data):
        data['units'][0]['positions'] = data['units'][0]['positions'][:1]
        data['announcement_level'].append({'field': '版本说明', 'value': '返回只覆盖部分岗位', 'status': 'UNKNOWN', 'evidence': []})
    preview = svc.ingest(svc.test_source, mutate_packet(two_positions_packet(), remove_one), actor='operator')
    svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', 'partial-update', actor='reviewer')
    after = {x['title']: x for x in svc.catalog(limit=50)['items']}
    assert '工程研究助理' in after
    assert '技术项目管理员' in after
    assert after['技术项目管理员']['id'] == before['技术项目管理员']
    assert after['技术项目管理员']['status'] == 'UPDATE_PENDING'


def test_business_code_identity_survives_wma_id_and_order_changes(svc):
    approve(svc, two_positions_packet(), 'stable-code-v1')
    before = {x['code']: x['id'] for x in svc.catalog(limit=50)['items']}

    def reorder(data):
        group=data['units'][0]
        group['id']='runtime-group-changed'
        group['positions']=list(reversed(group['positions']))
        group['positions'][0]['id']='runtime-position-z'
        group['positions'][1]['id']='runtime-position-y'
        data['announcement_level'].append({'field':'版本说明','value':'WMA重新枚举了内部ID','status':'UNKNOWN','evidence':[]})
    preview=svc.ingest(svc.test_source,mutate_packet(two_positions_packet(),reorder),actor='operator')
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'','stable-code-v2',actor='reviewer')
    catalog=svc.catalog(limit=50)
    assert catalog['total']==2
    assert all(x['status']=='CURRENT' for x in catalog['items'])
    after={x['code']:x['id'] for x in catalog['items']}
    assert before==after


def test_position_card_inherits_group_location_label_used_by_real_wma(svc):
    def change(data):
        data['units']=[{
            'id':'org-location','name':'浙江测试事业单位',
            'unit_level':[{'field':'单位所在地','value':'浙江杭州'}],
            'positions':[{'id':'pos-location','name':'信息技术岗','code':'X01','facts':[]}],
        }]
    approve(svc,mutate_packet(packet('事业单位集中招聘公告'),change),'group-location')
    card=svc.catalog(limit=50)['items'][0]
    assert card['region']=='浙江杭州'


def test_api_review_reports_action_targets_and_returns_target_receipt(svc):
    from fastapi.testclient import TestClient
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    app=create_app(Settings(database_url=svc.database_url,data_dir=svc.object_root.parent,public_catalog=True,allowed_hosts=['testserver']),product=svc)
    with TestClient(app) as client:
        login=client.post('/api/auth/login',json={'username':'operator','password':'long-password-123'}).json()
        client.headers['X-CSRF-Token']=login['csrf']
        received=client.post('/api/intake/'+svc.test_source,content=two_positions_packet(),headers={'Content-Type':'application/zip'}).json()
        review_login=client.post('/api/auth/login',json={'username':'reviewer','password':'long-password-123'}).json()
        client.headers['X-CSRF-Token']=review_login['csrf']
        preview=client.get('/api/review/'+received['id']).json()
        assert preview['scope']['opportunities']==1
        assert preview['scope']['action_targets']==2
        assert preview['scope']['children']==3
        decision=client.post('/api/review/'+received['id']+'/decision',json={
            'decision':'APPROVE','preview_hash':received['preview_hash'],'note':'','request_key':'api-two-targets'
        })
        assert decision.status_code==200,decision.text
        receipt=decision.json()
        assert len(receipt['public_ids'])==1
        assert len(receipt['catalog_target_ids'])==2
        catalog=client.get('/api/catalog?limit=50').json()
        assert catalog['total']==2
        assert {x['title'] for x in catalog['items']}=={'工程研究助理','技术项目管理员'}


def test_weak_fallback_identity_is_not_auto_merged_across_revisions(svc):
    def weak(data):
        data['units']=[{'name':'同名单位','positions':[{'name':'没有编号的助理岗','facts':[]}]}]
    first_blob=mutate_packet(packet('弱身份公告'),weak)
    approve(svc,first_blob,'weak-v1')
    first=svc.catalog(limit=50)['items'][0]
    def weak_changed(data):
        data['units']=[{'name':'同名单位','positions':[{'name':'没有编号的助理岗','facts':[]}]}]
        data['announcement_level'].append({'field':'版本说明','value':'第二版','status':'UNKNOWN','evidence':[]})
    preview=svc.ingest(svc.test_source,mutate_packet(packet('弱身份公告'),weak_changed),actor='operator')
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'','weak-v2',actor='reviewer')
    rows=svc.catalog(limit=50)['items']
    assert len(rows)==2
    assert first['id'] in {x['id'] for x in rows}
    assert {x['status'] for x in rows}=={'CURRENT','UPDATE_PENDING'}


def test_explicit_source_record_key_survives_runtime_id_change(svc):
    def v1(data):
        data['units']=[{'name':'稳定单位','positions':[{'id':'run-p1','source_record_key':'official-row-42','name':'无编号岗位','facts':[]}]}]
    approve(svc,mutate_packet(packet('稳定来源键公告'),v1),'source-key-v1')
    before=svc.catalog(limit=50)['items'][0]['id']
    def v2(data):
        data['units']=[{'name':'稳定单位','positions':[{'id':'run-p999','source_record_key':'official-row-42','name':'无编号岗位','facts':[]}]}]
        data['announcement_level'].append({'field':'版本说明','value':'运行时ID变化','status':'UNKNOWN','evidence':[]})
    preview=svc.ingest(svc.test_source,mutate_packet(packet('稳定来源键公告'),v2),actor='operator')
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'','source-key-v2',actor='reviewer')
    rows=svc.catalog(limit=50)['items']
    assert len(rows)==1 and rows[0]['id']==before and rows[0]['status']=='CURRENT'


def test_root_singleton_calendar_uses_catalog_target_identity(svc):
    blob = mutate_packet(packet('青年实践计划'), lambda data: data.update({'units': []}))
    approve(svc, blob, 'singleton-calendar')
    card = svc.catalog(limit=50)['items'][0]
    assert card['id'].startswith('opp_')
    calendar = svc.calendar(card['id']).decode('utf-8')
    assert 'BEGIN:VCALENDAR' in calendar
    assert 'UID:' in calendar and '@deepaha' in calendar
