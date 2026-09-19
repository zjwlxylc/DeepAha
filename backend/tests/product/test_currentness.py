import io
import json
import zipfile
from datetime import date, timedelta

from sqlalchemy import select

from .test_contract import svc


def day(n):
    return (date.today() + timedelta(days=n)).isoformat()


def currentness_packet(*, a_deadline=None, b_deadline=None, root_note='第一版共同说明', include_a=True,
                       include_b=True, a_lifecycle='ACTIVE', root_lifecycle='ACTIVE', a_artifact_text=None):
    a_deadline = a_deadline or day(40)
    b_deadline = b_deadline or day(50)
    a_text = a_artifact_text or f'A01 报名截止：{a_deadline}\n岗位 A01 仅限工程方向。\n'
    b_text = f'A02 报名截止：{b_deadline}\n岗位 A02 面向项目管理。\n'
    positions = []
    if include_a:
        positions.append({
            'id': 'run-a', 'source_record_key': 'official-position-A01', 'name': '工程研究助理', 'code': 'A01',
            'lifecycle_status': a_lifecycle,
            'facts': [
                {'field': '报名截止', 'value': a_deadline, 'status': 'CONFIRMED', 'evidence': [
                    {'artifact_id': 'a01', 'quote': f'A01 报名截止：{a_deadline}', 'locator': {'line': 1}}
                ]},
                {'field': '岗位描述', 'value': '参与工程研究。', 'status': 'CONFIRMED', 'evidence': [
                    {'artifact_id': 'a01', 'quote': '岗位 A01 仅限工程方向。', 'locator': {'line': 2}}
                ]},
            ],
        })
    if include_b:
        positions.append({
            'id': 'run-b', 'source_record_key': 'official-position-A02', 'name': '技术项目管理员', 'code': 'A02',
            'facts': [
                {'field': '报名截止', 'value': b_deadline, 'status': 'CONFIRMED', 'evidence': [
                    {'artifact_id': 'a02', 'quote': f'A02 报名截止：{b_deadline}', 'locator': {'line': 1}}
                ]},
                {'field': '岗位描述', 'value': '负责技术项目协调。', 'status': 'CONFIRMED', 'evidence': [
                    {'artifact_id': 'a02', 'quote': '岗位 A02 面向项目管理。', 'locator': {'line': 2}}
                ]},
            ],
        })
    data = {
        'source_record_key': 'notice-currentness-001',
        'opportunity_name': '海湾研究中心 2027 青年岗位公告',
        'publish_unit': '海湾研究中心',
        'opportunity_type': '招聘',
        'official_url': 'https://research.example.org/notices/currentness-001',
        'lifecycle_status': root_lifecycle,
        'announcement_level': [
            {'field': '公告说明', 'value': root_note, 'status': 'CONFIRMED', 'evidence': [
                {'artifact_id': 'root', 'quote': root_note, 'locator': {'line': 1}}
            ]},
        ],
        'units': [{
            'id': 'runtime-group', 'source_record_key': 'issuer-group', 'name': '海湾研究中心科研部', 'kind': 'GROUP',
            'positions': positions,
        }],
    }
    files = {
        'opportunities.json': json.dumps(data, ensure_ascii=False).encode(),
        'evidence.json': json.dumps({'artifacts': [
            {'artifact_id': 'root', 'local_path': 'artifacts/root.txt', 'url': data['official_url']},
            {'artifact_id': 'a01', 'local_path': 'artifacts/a01.txt', 'url': data['official_url'] + '#A01'},
            {'artifact_id': 'a02', 'local_path': 'artifacts/a02.txt', 'url': data['official_url'] + '#A02'},
        ]}, ensure_ascii=False).encode(),
        'report.md': b'# currentness test\n',
        'artifacts/root.txt': (root_note + '\n').encode(),
        'artifacts/a01.txt': a_text.encode(),
        'artifacts/a02.txt': b_text.encode(),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in files.items():
            z.writestr(name, value)
    return out.getvalue()


def approve(svc, blob, key):
    preview = svc.ingest(svc.test_source, blob, actor='operator')
    receipt = svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', key, actor='reviewer')
    return preview, receipt


def targets(svc):
    return {x['code']: x for x in svc.catalog(limit=50)['items']}


def test_one_position_deadline_correction_only_invalidates_that_target_and_reminder(svc):
    from deepaha.product.models import TargetNotice
    first_a, first_b = day(40), day(50)
    approve(svc, currentness_packet(a_deadline=first_a, b_deadline=first_b), 'sg3-initial')
    before = targets(svc)
    svc.set_action(before['A01']['id'], 'SAVED', actor='reader')
    svc.set_action(before['A02']['id'], 'SAVED', actor='reader')
    svc.set_reminder(before['A01']['id'], actor='reader')
    svc.set_reminder(before['A02']['id'], actor='reader')

    preview = svc.ingest(svc.test_source, currentness_packet(a_deadline=day(60), b_deadline=first_b), actor='operator')
    after = targets(svc)
    assert after['A01']['status'] == 'UPDATE_PENDING'
    assert after['A01']['deadline'] is None
    assert after['A02']['status'] == 'CURRENT'
    assert after['A02']['deadline'] == first_b
    changes = preview['opportunities'][0]['currentness']
    assert changes['counts']['changed'] == 1
    assert changes['counts']['unchanged'] == 1
    assert changes['targets'][0]['public_id'] == before['A01']['id']
    assert 'deadline' in changes['targets'][0]['affected_fields']
    with svc.db.tx(False) as s:
        notice_state = {n.target_public_id: n.state for n in s.scalars(select(TargetNotice).where(TargetNotice.kind == 'DEADLINE'))}
    assert notice_state[before['A01']['id']] == 'CANCELLED'
    assert notice_state[before['A02']['id']] != 'CANCELLED'


def test_root_common_correction_affects_both_descendants(svc):
    approve(svc, currentness_packet(), 'sg3-root-initial')
    preview = svc.ingest(svc.test_source, currentness_packet(root_note='第二版共同说明'), actor='operator')
    rows = targets(svc)
    assert {x['status'] for x in rows.values()} == {'UPDATE_PENDING'}
    currentness = preview['opportunities'][0]['currentness']
    assert currentness['counts']['changed'] == 2
    assert all(any('common_fields' in f for f in t['affected_fields']) for t in currentness['targets'])


def test_missing_child_is_pending_not_withdrawn_before_and_after_approval(svc):
    approve(svc, currentness_packet(), 'sg3-missing-initial')
    before = targets(svc)
    preview = svc.ingest(svc.test_source, currentness_packet(include_b=False), actor='operator')
    during = targets(svc)
    assert during['A02']['status'] == 'UPDATE_PENDING'
    change = next(x for x in preview['opportunities'][0]['currentness']['targets'] if x['public_id'] == before['A02']['id'])
    assert change['change_kind'] == 'MISSING_PENDING'
    svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', 'sg3-missing-update', actor='reviewer')
    after = targets(svc)
    assert after['A02']['status'] == 'UPDATE_PENDING'
    assert after['A02']['id'] == before['A02']['id']


def test_explicit_child_withdrawal_only_withdraws_that_target_after_approval(svc):
    approve(svc, currentness_packet(), 'sg3-withdraw-initial')
    before = targets(svc)
    preview = svc.ingest(svc.test_source, currentness_packet(a_lifecycle='WITHDRAWN'), actor='operator')
    during = targets(svc)
    assert during['A01']['status'] == 'UPDATE_PENDING'
    assert during['A02']['status'] == 'CURRENT'
    change = next(x for x in preview['opportunities'][0]['currentness']['targets'] if x['public_id'] == before['A01']['id'])
    assert change['change_kind'] == 'WITHDRAWAL_PENDING'
    svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', 'sg3-withdraw-approve', actor='reviewer')
    after = targets(svc)
    assert 'A01' not in after
    assert after['A02']['status'] == 'CURRENT'
    history = svc.target_history(before['A01']['id'])
    assert history['current_status'] == 'WITHDRAWN'


def test_attachment_replacement_only_invalidates_target_using_that_artifact(svc):
    approve(svc, currentness_packet(), 'sg3-artifact-initial')
    before = targets(svc)
    # Same extracted facts and quote, changed raw bytes for only A01 evidence material.
    replacement = currentness_packet(a_artifact_text=f'A01 报名截止：{day(40)}\n岗位 A01 仅限工程方向。\n附件版本：2\n')
    preview = svc.ingest(svc.test_source, replacement, actor='operator')
    after = targets(svc)
    assert after['A01']['status'] == 'UPDATE_PENDING'
    assert after['A02']['status'] == 'CURRENT'
    change = next(x for x in preview['opportunities'][0]['currentness']['targets'] if x['public_id'] == before['A01']['id'])
    assert change['change_kind'] == 'EVIDENCE_REPLACED'
    assert any(x.startswith('evidence:') for x in change['affected_fields'])


def test_approved_correction_creates_target_history_and_compare(svc):
    first = day(40); second = day(70)
    approve(svc, currentness_packet(a_deadline=first), 'sg3-history-initial')
    tid = targets(svc)['A01']['id']
    preview = svc.ingest(svc.test_source, currentness_packet(a_deadline=second), actor='operator')
    svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', 'sg3-history-v2', actor='reviewer')
    assert targets(svc)['A01']['deadline'] == second
    history = svc.target_history(tid)
    assert len(history['versions']) >= 2
    newest, older = history['versions'][0], history['versions'][1]
    compared = svc.compare_target_versions(tid, older['catalog_target_id'], newest['catalog_target_id'])
    assert compared['changes']['deadline'] == {'before': first, 'after': second}
    assert compared['target_public_id'] == tid


def test_rejected_correction_does_not_reactivate_stale_deadline_or_reminder(svc):
    from deepaha.product.models import TargetNotice
    approve(svc, currentness_packet(), 'sg3-reject-initial')
    tid = targets(svc)['A01']['id']
    svc.set_action(tid, 'SAVED', actor='reader')
    svc.set_reminder(tid, actor='reader')
    preview = svc.ingest(svc.test_source, currentness_packet(a_deadline=day(80)), actor='operator')
    svc.decide(preview['id'], 'REJECT', preview['preview_hash'], '更正包暂不能收录，需要复查', 'sg3-reject-update', actor='reviewer')
    assert svc.detail(tid)['status'] == 'UPDATE_PENDING'
    assert svc.detail(tid)['deadline'] is None
    with svc.db.tx(False) as s:
        rows = list(s.scalars(select(TargetNotice).where(TargetNotice.target_public_id == tid, TargetNotice.kind == 'DEADLINE')))
    assert rows and all(x.state == 'CANCELLED' for x in rows)


def test_targeted_recheck_creates_scoped_recheck_task(svc):
    approve(svc, currentness_packet(), 'sg3-recheck-initial')
    tid = targets(svc)['A01']['id']
    svc.ingest(svc.test_source, currentness_packet(a_deadline=day(90)), actor='operator')
    task = svc.create_targeted_recheck(tid, actor='operator', request_key='sg3-targeted-recheck')
    assert task['kind'] == 'RECHECK'
    assert tid in task['instruction']
    assert '报名截止' in task['instruction'] or 'deadline' in task['instruction']
    assert 'A02' not in task['instruction']


def test_periodic_source_check_uses_recheck_semantics(svc):
    from deepaha.product.models import SourceProfile, now
    from deepaha.product.worker import schedule_due
    svc.schedule_source(svc.test_source, 6, actor='operator')
    with svc.db.tx() as s:
        s.get(SourceProfile, svc.test_source).next_due = now() - timedelta(seconds=1)
    assert schedule_due(svc) == 1
    task = svc.tasks(actor='operator')[0]
    assert task['kind'] == 'RECHECK'
    assert '更正' in task['instruction'] and '撤回' in task['instruction'] and '附件替换' in task['instruction']

def test_explicit_root_withdrawal_withdraws_all_targets_only_after_approval(svc):
    approve(svc,currentness_packet(),'sg3-root-withdraw-initial')
    before=targets(svc)
    preview=svc.ingest(svc.test_source,currentness_packet(root_lifecycle='WITHDRAWN'),actor='operator')
    during=targets(svc)
    assert set(during)=={'A01','A02'}
    assert {x['status'] for x in during.values()}=={'UPDATE_PENDING'}
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'','sg3-root-withdraw-approve',actor='reviewer')
    assert svc.catalog(limit=50)['total']==0
    assert all(svc.target_history(x['id'])['current_status']=='WITHDRAWN' for x in before.values())

def test_legacy_projection_without_lifecycle_status_defaults_active():
    from deepaha.product.adapter import public_content
    item={
        'title':'旧版机会','type':'RESEARCH_PROGRAM','issuer':'旧机构','source_name':'旧来源',
        'official_url':'https://research.example.org/legacy','application_url':'','region':'','summary':'',
        'deadline':None,'deadline_precision':None,'eligibility':'UNCERTAIN','raw_type':'科研',
        'fields':[],'children':[],'notes':[],
    }
    out=public_content(item,[])
    assert out['lifecycle_status']=='ACTIVE'


def test_lifecycle_metadata_is_not_exposed_as_business_field(svc):
    preview = svc.ingest(svc.test_source, currentness_packet(a_lifecycle='WITHDRAWN'), actor='operator')
    children = preview['opportunities'][0]['children']
    position = next(x for x in children if x['code'] == 'A01')
    labels = {f['label'] for f in position['fields']}
    assert 'lifecycle_status' not in labels
    assert 'opportunity_status' not in labels
    assert 'status' not in labels
    assert position['lifecycle_status'] == 'WITHDRAWN'
