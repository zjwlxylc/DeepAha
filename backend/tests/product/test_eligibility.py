import io
import json
import zipfile
from datetime import date, timedelta

from openpyxl import Workbook

from .test_contract import svc


def _zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, value in files.items():
            z.writestr(name, value)
    return out.getvalue()


def eligibility_packet(*, facts, coverage=None, deadline=None, text_lines=None, root_facts=None, title='资格判断测试公告'):
    official='https://research.example.org/notices/eligibility'
    root={
        'opportunity_name':title,
        'publish_unit':'海湾研究中心',
        'opportunity_type':'PUBLIC_INSTITUTION_JOB',
        'official_url':official,
        'announcement_level':list(root_facts or []),
        'units':[{'id':'g1','name':'测试单位','positions':[{'id':'p1','name':'资格测试岗','code':'E01','facts':facts}]}],
    }
    if coverage:
        root['metadata']={'qualification_coverage':coverage}
    if deadline:
        root['registration_deadline']=deadline
        root['announcement_level'].append({
            'field':'报名截止','value':deadline,'status':'CONFIRMED',
            'evidence':[{'artifact_id':'a1','quote':'报名截止：'+deadline,'locator':{'line':1}}],
        })
    lines=list(text_lines or [])
    if deadline:
        lines.insert(0,'报名截止：'+deadline)
    body='\n'.join(lines)+'\n'
    return _zip({
        'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),
        'evidence.json':json.dumps({'artifacts':[{'artifact_id':'a1','local_path':'artifacts/notice.txt','url':official}]},ensure_ascii=False).encode(),
        'report.md':b'# eligibility fixture',
        'artifacts/notice.txt':body.encode(),
    })


def approve(svc, blob, key):
    preview=svc.ingest(svc.test_source,blob,actor='operator')
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'',key,actor='reviewer')
    return svc.catalog(limit=50)['items'][0]['id']


def hard_fact(label,value,quote=None,state='CONFIRMED'):
    evidence=[] if quote is None else [{'artifact_id':'a1','quote':quote,'locator':{'line':1}}]
    return {'field':label,'value':value,'status':state,'evidence':evidence}


def test_located_hard_conflict_can_be_ineligible(svc):
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('学历','硕士研究生以上','学历：硕士研究生以上')],
        text_lines=['学历：硕士研究生以上'],
    ),'eligibility-conflict')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    assert fit['decision_basis']=='DETERMINISTIC_EVIDENCE_BACKED'
    conflict=next(x for x in fit['requirements'] if x['type']=='EDUCATION_MIN')
    assert conflict['outcome']=='CONFLICT'
    assert conflict['evidence_support']=='LOCATED'


def test_same_unlocated_conflict_must_remain_uncertain(svc):
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('学历','硕士研究生以上',None)],
    ),'eligibility-unlocated')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert not fit['hard_conflicts']
    assert 'EVIDENCE_UNLOCATED' in fit['review_reasons']


def test_satisfied_conditions_without_explicit_coverage_are_likely_eligible(svc):
    future=(date.today()+timedelta(days=60)).isoformat()
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('学历','本科及以上','学历：本科及以上'), hard_fact('毕业届别','2027届毕业生','届别：2027届毕业生')],
        deadline=future,
        text_lines=['学历：本科及以上','届别：2027届毕业生'],
    ),'eligibility-likely')
    svc.set_profile({'education':'本科','graduation_year':2027},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='LIKELY_ELIGIBLE'
    assert fit['coverage']['state']=='BOUNDED'
    assert all(x['outcome']=='SATISFIED' for x in fit['requirements'])


def test_explicit_complete_coverage_all_satisfied_is_eligible(svc):
    future=(date.today()+timedelta(days=60)).isoformat()
    oid=approve(svc,eligibility_packet(
        coverage='COMPLETE',
        facts=[hard_fact('学历','本科及以上','学历：本科及以上'), hard_fact('毕业届别','2027届毕业生','届别：2027届毕业生')],
        deadline=future,
        text_lines=['学历：本科及以上','届别：2027届毕业生'],
    ),'eligibility-complete')
    svc.set_profile({'education':'本科','graduation_year':2027},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='ELIGIBLE'
    assert fit['coverage']['state']=='COMPLETE'


def test_missing_profile_and_generic_fresh_graduate_are_uncertain(svc):
    oid=approve(svc,eligibility_packet(
        coverage='COMPLETE',
        facts=[hard_fact('招聘对象类别','应届毕业生','招聘对象：应届毕业生')],
        text_lines=['招聘对象：应届毕业生'],
    ),'eligibility-generic-fresh')
    svc.set_profile({'graduation_year':2027},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert 'SEMANTIC_NOT_DETERMINISTIC' in fit['review_reasons']


def test_exception_language_never_creates_hard_denial(svc):
    oid=approve(svc,eligibility_packet(
        coverage='COMPLETE',
        facts=[hard_fact('学历','硕士研究生以上；具有高级职称者可放宽','学历：硕士研究生以上；具有高级职称者可放宽')],
        text_lines=['学历：硕士研究生以上；具有高级职称者可放宽'],
    ),'eligibility-exception')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert not fit['hard_conflicts']
    assert 'EXCEPTION_OR_ALTERNATIVE_PRESENT' in fit['review_reasons']


def test_explicit_major_code_prefix_can_safely_conflict(svc):
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('专业','理学（07）、工学（08）','专业：理学（07）、工学（08）')],
        text_lines=['专业：理学（07）、工学（08）'],
    ),'eligibility-major')
    svc.set_profile({'major':'广告学','major_code':'050303'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    rule=next(x for x in fit['requirements'] if x['type']=='MAJOR_CODE_SET')
    assert rule['normalized']['allowed_prefixes']==['07','08']
    assert rule['outcome']=='CONFLICT'


def test_xlsx_cell_locator_can_support_hard_conflict(svc):
    wb=Workbook();ws=wb.active;ws.title='岗位信息表';ws['K5']='硕士研究生以上'
    buf=io.BytesIO();wb.save(buf)
    official='https://research.example.org/notices/xlsx'
    root={
        'opportunity_name':'XLSX资格测试','publish_unit':'海湾研究中心','opportunity_type':'PUBLIC_INSTITUTION_JOB','official_url':official,
        'units':[{'id':'g1','name':'测试单位','positions':[{'id':'p1','name':'表格岗位','code':'X01','facts':[
            {'field':'学历','value':'硕士研究生以上','status':'CONFIRMED','evidence':[{'artifact_id':'xlsx1','quote':'硕士研究生以上','locator':{'sheet':'岗位信息表','row':5,'column':'K'}}]}
        ]}]}],
    }
    blob=_zip({
        'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),
        'evidence.json':json.dumps({'artifacts':[{'artifact_id':'xlsx1','local_path':'artifacts/plan.xlsx','url':official}]},ensure_ascii=False).encode(),
        'report.md':b'# xlsx',
        'artifacts/plan.xlsx':buf.getvalue(),
    })
    oid=approve(svc,blob,'eligibility-xlsx')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    rule=next(x for x in fit['requirements'] if x['type']=='EDUCATION_MIN')
    assert rule['evidence_support']=='LOCATED'
    assert rule['evidence'][0]['verification']=='XLSX_CELL_MATCH'


def test_expired_evidence_backed_window_is_ineligible(svc):
    past=(date.today()-timedelta(days=10)).isoformat()
    oid=approve(svc,eligibility_packet(
        coverage='COMPLETE',facts=[],deadline=past,
    ),'eligibility-expired')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    deadline=next(x for x in fit['requirements'] if x['type']=='APPLICATION_DEADLINE')
    assert deadline['outcome']=='CONFLICT'
    assert deadline['reason_code']=='APPLICATION_WINDOW_CLOSED'


def test_update_pending_caps_eligibility_to_uncertain(svc):
    oid=approve(svc,eligibility_packet(
        coverage='COMPLETE',facts=[hard_fact('学历','硕士研究生以上','学历：硕士研究生以上')],
        text_lines=['学历：硕士研究生以上'],
    ),'eligibility-current-v1')
    svc.set_profile({'education':'本科'},actor='reader')
    from deepaha.product.models import CatalogTarget
    from sqlalchemy import select
    with svc.db.tx() as s:
        target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==oid,CatalogTarget.status=='CURRENT'))
        target.status='UPDATE_PENDING'
        body=dict(target.content);body['currentness']={'change_kind':'FIELD_CHANGE','affected_fields':['fields:学历#1'],'summary':'学历条件有新版本待收录'};target.content=body
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert 'TARGET_UPDATE_PENDING' in fit['review_reasons']
    assert not fit['hard_conflicts']


def test_unsupported_hard_condition_blocks_positive_but_not_negative(svc):
    oid=approve(svc,eligibility_packet(
        coverage='COMPLETE',facts=[hard_fact('其他条件','须具有两年相关一线工作经历','其他条件：须具有两年相关一线工作经历')],
        text_lines=['其他条件：须具有两年相关一线工作经历'],
    ),'eligibility-unsupported-hard')
    svc.set_profile({'education':'博士研究生'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert 'UNSUPPORTED_HARD_CONDITION' in fit['review_reasons']


def test_profile_accepts_sg4_optional_attributes_and_rejects_bad_values(svc):
    from deepaha.product.errors import Problem
    saved=svc.set_profile({
        'education':'本科','major':'广告学','major_code':'050303','graduation_year':2027,
        'birth_date':'2004-06-01','hukou_region':'浙江省宁波市'
    },actor='reader')
    assert saved['major_code']=='050303'
    assert saved['birth_date']=='2004-06-01'
    assert saved['hukou_region']=='浙江省宁波市'
    import pytest
    with pytest.raises(Problem):svc.set_profile({'birth_date':'2004-99-99'},actor='reader')
    with pytest.raises(Problem):svc.set_profile({'major_code':'新闻传播'},actor='reader')


def test_age_context_is_not_a_global_cutoff_for_other_age_limits(svc):
    root_age=hard_fact('年龄要求','38周岁以下专指1987年8月12日及以后出生','年龄说明：38周岁以下专指1987年8月12日及以后出生')
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('年龄','43周岁以下','年龄：43周岁以下')],
        root_facts=[root_age],
        text_lines=['年龄说明：38周岁以下专指1987年8月12日及以后出生','年龄：43周岁以下'],
    ),'eligibility-age-context-not-global')
    svc.set_profile({'birth_date':'1985-01-01'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert not fit['hard_conflicts']


def test_matching_age_context_uses_both_located_evidence_items(svc):
    root_age=hard_fact('年龄要求','38周岁以下专指1987年8月12日及以后出生','年龄说明：38周岁以下专指1987年8月12日及以后出生')
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('年龄','38周岁以下','年龄：38周岁以下')],
        root_facts=[root_age],
        text_lines=['年龄说明：38周岁以下专指1987年8月12日及以后出生','年龄：38周岁以下'],
    ),'eligibility-age-context-located')
    svc.set_profile({'birth_date':'1985-01-01'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    age=next(x for x in fit['requirements'] if x['type']=='BIRTH_DATE_MIN')
    assert age['outcome']=='CONFLICT'
    assert len(age['evidence'])==2
    assert all(x['located'] for x in age['evidence'])


def test_matching_age_context_with_unlocated_helper_stays_uncertain(svc):
    root_age=hard_fact('年龄要求','38周岁以下专指1987年8月12日及以后出生',None)
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('年龄','38周岁以下','年龄：38周岁以下')],
        root_facts=[root_age],
        text_lines=['年龄：38周岁以下'],
    ),'eligibility-age-context-unlocated')
    svc.set_profile({'birth_date':'1985-01-01'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert not fit['hard_conflicts']
    assert 'EVIDENCE_UNLOCATED' in fit['review_reasons']


def test_explicit_hukou_region_can_safely_conflict(svc):
    oid=approve(svc,eligibility_packet(
        facts=[hard_fact('户籍要求','浙江省户籍','户籍要求：浙江省户籍')],
        text_lines=['户籍要求：浙江省户籍'],
    ),'eligibility-hukou')
    svc.set_profile({'hukou_region':'江苏省南京市'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    rule=next(x for x in fit['requirements'] if x['type']=='HUKOU_REGION')
    assert rule['outcome']=='CONFLICT'

def test_corrupt_xlsx_evidence_fails_closed_as_uncertain(svc):
    official='https://research.example.org/notices/corrupt-xlsx'
    root={
        'opportunity_name':'损坏表格资格测试','publish_unit':'海湾研究中心','opportunity_type':'PUBLIC_INSTITUTION_JOB','official_url':official,
        'units':[{'id':'g1','name':'测试单位','positions':[{'id':'p1','name':'损坏表格岗位','code':'X02','facts':[
            {'field':'学历','value':'硕士研究生以上','status':'CONFIRMED','evidence':[{'artifact_id':'xlsx1','quote':'硕士研究生以上','locator':{'sheet':'岗位信息表','row':5,'column':'K'}}]}
        ]}]}],
    }
    blob=_zip({
        'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),
        'evidence.json':json.dumps({'artifacts':[{'artifact_id':'xlsx1','local_path':'artifacts/plan.xlsx','url':official}]},ensure_ascii=False).encode(),
        'report.md':b'# corrupt xlsx',
        'artifacts/plan.xlsx':b'not-a-real-xlsx-file',
    })
    oid=approve(svc,blob,'eligibility-corrupt-xlsx')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert not fit['hard_conflicts']
    assert 'EVIDENCE_UNLOCATED' in fit['review_reasons']
