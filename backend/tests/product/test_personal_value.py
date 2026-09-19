import io
import json
import zipfile
from datetime import date, timedelta

from .test_contract import svc


def _zip(data, body=''):
    official=data['official_url']
    files={
        'opportunities.json':json.dumps(data,ensure_ascii=False).encode(),
        'evidence.json':json.dumps({'artifacts':[{'artifact_id':'a1','local_path':'artifacts/notice.txt','url':official}]},ensure_ascii=False).encode(),
        'report.md':('# '+data['opportunity_name']).encode(),
        'artifacts/notice.txt':body.encode(),
    }
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for k,v in files.items(): z.writestr(k,v)
    return out.getvalue()


def opportunity_packet(title, *, typ='YOUTH_POLICY_BENEFIT', region='宁波', summary='', deadline=None,
                       unit_name=None, facts=None, root_fields=None, coverage=None):
    official='https://research.example.org/notices/'+str(abs(hash((title,typ)))%100000)
    root={
        'opportunity_name':title,
        'publish_unit':'测试机会中心',
        'opportunity_type':typ,
        'official_url':official,
        'work_location':region,
        'summary':summary,
        'announcement_level':list(root_fields or []),
    }
    if coverage:
        root['metadata']={'qualification_coverage':coverage}
    if deadline:
        root['registration_deadline']=deadline
        root['announcement_level'].append({
            'field':'报名截止','value':deadline,'status':'CONFIRMED',
            'evidence':[{'artifact_id':'a1','quote':'报名截止：'+deadline,'locator':{'line':1}}],
        })
    unit_name=unit_name or title
    facts=list(facts or [])
    if typ in {'PUBLIC_INSTITUTION_JOB','STATE_OWNED_ENTERPRISE_JOB'}:
        root['units']=[{'id':'g1','name':'测试单位','positions':[{'id':'p1','name':unit_name,'facts':facts}]}]
    elif typ=='COMPETITION':
        root['tracks']=[{'id':'t1','name':unit_name,'kind':'TRACK','facts':facts}]
    else:
        root['program_tiers']=[{'id':'x1','name':unit_name,'kind':'PROGRAM_TIER','facts':facts}]
    lines=[]
    if deadline: lines.append('报名截止：'+deadline)
    for f in facts:
        for ev in f.get('evidence',[]):
            if ev.get('quote'): lines.append(ev['quote'])
    return _zip(root,'\n'.join(lines)+'\n')


def fact(label,value,quote=None):
    return {'field':label,'value':value,'status':'CONFIRMED','evidence':([{'artifact_id':'a1','quote':quote,'locator':{'line':1}}] if quote else [])}


def approve(svc, blob, key):
    p=svc.ingest(svc.test_source,blob,actor='operator')
    assert p['can_approve']
    svc.decide(p['id'],'APPROVE',p['preview_hash'],'',key,actor='reviewer')
    return svc.catalog(limit=50)['items'][0]['id']


def test_progressive_profile_accepts_sg5_fields_and_can_disable_personalization(svc):
    saved=svc.set_profile({
        'education':'本科','major':'广告学','cities':['宁波'],
        'opportunity_types':['YOUTH_POLICY_BENEFIT','COMPETITION'],
        'career_directions':['AI产品运营'],
        'constraints':['不接受长期异地'],
        'region_preference_mode':'PREFERRED',
        'personalization_enabled':False,
    },actor='reader')
    assert saved['opportunity_types']==['YOUTH_POLICY_BENEFIT','COMPETITION']
    assert saved['career_directions']==['AI产品运营']
    assert saved['personalization_enabled'] is False
    result=svc.recommendations(actor='reader')
    assert result['personalization_enabled'] is False
    assert result['items']==[]


def test_hard_ineligible_is_filtered_but_uncertain_is_not(svc):
    good=opportunity_packet('宁波青年创新补贴',summary='支持青年创新实践项目')
    bad=opportunity_packet(
        '宁波青年专项岗位',typ='PUBLIC_INSTITUTION_JOB',unit_name='政策运营岗',summary='青年政策运营',
        facts=[fact('学历','硕士研究生以上','学历：硕士研究生以上')],
    )
    approve(svc,good,'sg5-good')
    approve(svc,bad,'sg5-bad')
    svc.set_profile({
        'education':'本科','cities':['宁波'],'interests':['青年创新'],
        'opportunity_types':['YOUTH_POLICY_BENEFIT','PUBLIC_INSTITUTION_JOB'],
        'personalization_enabled':True,
    },actor='reader')
    r=svc.recommendations(actor='reader',limit=20)
    titles=[x['title'] for x in r['items']]
    assert '宁波青年创新补贴' in titles
    assert '政策运营岗' not in titles
    assert r['excluded_ineligible']>=1
    assert all(x['eligibility_status']!='INELIGIBLE' for x in r['items'])


def test_type_region_goal_and_timing_create_explainable_priority_without_fake_score(svc):
    soon=(date.today()+timedelta(days=8)).isoformat()
    later=(date.today()+timedelta(days=80)).isoformat()
    approve(svc,opportunity_packet('青年项目支持',region='宁波',summary='AIGC内容创新项目支持',deadline=soon,unit_name='宁波AIGC青年创新支持'),'sg5-near')
    approve(svc,opportunity_packet('青年项目支持远期',region='杭州',summary='普通创业项目支持',deadline=later,unit_name='杭州普通创业支持'),'sg5-far')
    svc.set_profile({
        'education':'本科','cities':['宁波'],'interests':['AIGC'],'goals':['积累项目经历'],
        'career_directions':['AI产品运营'],'opportunity_types':['YOUTH_POLICY_BENEFIT'],
        'region_preference_mode':'PREFERRED','personalization_enabled':True,
    },actor='reader')
    r=svc.recommendations(actor='reader',limit=10)
    assert r['basis']=='LOCAL_VALUE_PRIORITY_V1'
    assert r['llm_used'] is False
    assert r['items'][0]['title']=='宁波AIGC青年创新支持'
    top=r['items'][0]
    assert top['priority_band'] in {'ACT_NOW','HIGH'}
    assert top['why_for_you']
    assert top['why_now'] and ('8' in top['why_now'] or '报名' in top['why_now'])
    assert 'value_score' not in top and 'success_probability' not in top and 'match_percent' not in top
    assert top['eligibility_status'] in {'ELIGIBLE','LIKELY_ELIGIBLE','UNCERTAIN'}


def test_unknown_time_does_not_create_fake_urgency(svc):
    approve(svc,opportunity_packet('常年青年安居计划',region='宁波',summary='常年受理',unit_name='北区安居支持',root_fields=[{'field':'受理时间','value':'常年受理，额度用完即止','status':'UNKNOWN','evidence':[]}]),'sg5-rolling')
    svc.set_profile({'cities':['宁波'],'opportunity_types':['YOUTH_POLICY_BENEFIT'],'personalization_enabled':True},actor='reader')
    item=svc.recommendations(actor='reader',limit=5)['items'][0]
    assert item['why_now'] in {'时间节点尚未明确，先确认当前官方安排。','当前没有可靠的精确截止时间。'}
    assert item['priority_band']!='ACT_NOW'


def test_selected_opportunity_type_beats_superficial_keyword_match(svc):
    approve(svc,opportunity_packet('宁波政策传播招聘',typ='PUBLIC_INSTITUTION_JOB',region='宁波',summary='负责青年政策传播与活动运营',unit_name='青年政策传播岗'),'sg5-keyword-job')
    approve(svc,opportunity_packet('一次性求职补贴',typ='YOUTH_POLICY_BENEFIT',region='宁波',summary='面向毕业生的一次性求职补贴',unit_name='宁波一次性求职补贴'),'sg5-policy')
    svc.set_profile({
        'cities':['宁波'],'interests':['政策'],'goals':['获得求职支持'],
        'opportunity_types':['YOUTH_POLICY_BENEFIT'],'personalization_enabled':True,
    },actor='reader')
    r=svc.recommendations(actor='reader',limit=5)
    assert r['items'] and all(x['type']=='YOUTH_POLICY_BENEFIT' for x in r['items'])
    assert r['items'][0]['title']=='宁波一次性求职补贴'


def test_dismissed_and_completed_targets_leave_discovery_but_saved_can_remain(svc):
    ids=[]
    for i in range(3):
        approve(svc,opportunity_packet(f'宁波青年项目{i}',summary='青年创新项目',unit_name=f'项目{i}'),'sg5-action-'+str(i))
        ids.append(svc.catalog(q=f'项目{i}',limit=10)['items'][0]['id'])
    svc.set_action(ids[0],'DISMISSED',actor='reader')
    svc.set_action(ids[1],'COMPLETED',actor='reader')
    svc.set_action(ids[2],'SAVED',actor='reader')
    svc.set_profile({'cities':['宁波'],'interests':['青年创新'],'opportunity_types':['YOUTH_POLICY_BENEFIT'],'personalization_enabled':True},actor='reader')
    r=svc.recommendations(actor='reader',limit=10)
    got={x['id'] for x in r['items']}
    assert ids[0] not in got and ids[1] not in got
    assert ids[2] in got


def test_top_n_diversifies_roots_when_profile_is_not_single_type_locked(svc):
    # One announcement produces several closely related targets; another root should still surface.
    official='https://research.example.org/notices/many-tracks'
    root={
        'opportunity_name':'AI挑战赛','publish_unit':'竞赛委员会','opportunity_type':'COMPETITION','official_url':official,'work_location':'浙江',
        'tracks':[{'id':f't{i}','name':f'AI赛道{i}','kind':'TRACK','facts':[{'field':'赛题','value':'AI产品创新','status':'UNKNOWN','evidence':[]}]} for i in range(5)],
        'announcement_level':[],
    }
    p=svc.ingest(svc.test_source,_zip(root),actor='operator');svc.decide(p['id'],'APPROVE',p['preview_hash'],'','sg5-many',actor='reviewer')
    approve(svc,opportunity_packet('宁波AI实践计划',typ='YOUTH_DEVELOPMENT_PROGRAM',region='宁波',summary='AI产品实践',unit_name='AI产品实践'),'sg5-other-root')
    svc.set_profile({'cities':['宁波'],'interests':['AI'],'goals':['积累项目经历'],'personalization_enabled':True},actor='reader')
    r=svc.recommendations(actor='reader',limit=5)
    roots=[x['root_public_id'] for x in r['featured']]
    assert len(set(roots))>=2


def test_value_detail_uses_same_engine_and_has_risks(svc):
    oid=approve(svc,opportunity_packet('宁波青年科研实践',typ='RESEARCH_PROGRAM',region='宁波',summary='科研实践项目',unit_name='传播研究方向'),'sg5-value-detail')
    svc.set_profile({'cities':['宁波'],'interests':['科研'],'goals':['积累研究经历'],'personalization_enabled':True},actor='reader')
    detail=svc.value(oid,actor='reader')
    assert detail['target_id']==oid
    assert detail['why_for_you']
    assert detail['why_now']
    assert detail['risks']
    assert detail['llm_used'] is False
    assert 'score' not in json.dumps(detail).lower()


def test_candidate_pool_is_bounded_and_reports_diagnostics(svc):
    for i in range(25):
        approve(svc,opportunity_packet(f'机会{i}',region='宁波',summary='普通青年机会',unit_name=f'机会{i}'),f'sg5-pool-{i}')
    svc.set_profile({'cities':['宁波'],'personalization_enabled':True},actor='reader')
    r=svc.recommendations(actor='reader',limit=5)
    assert r['candidate_limit']<=120
    assert r['candidate_count']<=r['candidate_limit']
    assert r['evaluated_count']<=r['candidate_limit']


def test_priority_output_is_deterministic_for_same_profile_and_catalog(svc):
    for title in ['宁波创新实践A','宁波创新实践B','杭州创新实践C']:
        approve(svc,opportunity_packet(title,region='宁波' if '宁波' in title else '杭州',summary='AI创新实践',unit_name=title),key='sg5-stable-'+title)
    svc.set_profile({'cities':['宁波'],'interests':['AI'],'goals':['创新实践'],'personalization_enabled':True},actor='reader')
    a=svc.recommendations(actor='reader',limit=10)
    b=svc.recommendations(actor='reader',limit=10)
    assert [x['id'] for x in a['items']]==[x['id'] for x in b['items']]
    assert [x['priority_band'] for x in a['items']]==[x['priority_band'] for x in b['items']]

def test_curated_top_n_beats_legacy_keyword_baseline(svc):
    # Curated SG5 calibration: for a user who explicitly selects policy/benefit,
    # two policy benefits are relevant; a job that merely contains the word
    # “政策” is a superficial keyword false positive.
    approve(svc,opportunity_packet('宁波政策传播招聘',typ='PUBLIC_INSTITUTION_JOB',region='宁波',summary='负责青年政策传播',unit_name='青年政策传播岗'),'sg5-bench-job')
    approve(svc,opportunity_packet('一次性求职补贴',typ='YOUTH_POLICY_BENEFIT',region='宁波',summary='面向毕业生发放一次性求职补贴',unit_name='一次性求职补贴'),'sg5-bench-policy1')
    approve(svc,opportunity_packet('青年安居支持',typ='YOUTH_POLICY_BENEFIT',region='宁波',summary='符合条件青年可申请租房支持',unit_name='青年安居支持'),'sg5-bench-policy2')
    profile={'cities':['宁波'],'interests':['政策'],'opportunity_types':['YOUTH_POLICY_BENEFIT'],'personalization_enabled':True}
    svc.set_profile(profile,actor='reader')
    all_rows=svc.catalog(limit=50)['items']
    relevant={x['id'] for x in all_rows if x['type']=='YOUTH_POLICY_BENEFIT'}

    # Reproduce the rc2/SG4 preference-text baseline exactly enough for this
    # calibration: text hit + city hit, no type semantics and no eligibility.
    def old_score(c):
        detail=svc.detail(c['id'])
        body=detail['title']+' '+(detail.get('summary') or '')+' '+' '.join(str(f.get('value','')) for f in detail.get('fields',[])+detail.get('ancestor_fields',[])+detail.get('common_fields',[]))
        score=0
        for term in profile['interests']:
            if term.casefold() in body.casefold():score+=2
        for city in profile['cities']:
            if city in (detail.get('region') or ''):score+=1
        return score
    baseline=sorted(all_rows,key=lambda c:(-old_score(c),c['id']))[:2]
    baseline_precision=sum(x['id'] in relevant for x in baseline)/2
    sg5=svc.recommendations(actor='reader',limit=2)['items']
    sg5_precision=sum(x['id'] in relevant for x in sg5)/2
    assert sg5_precision==1.0
    assert sg5_precision>baseline_precision

def test_progressive_profile_infers_policy_type_before_user_selects_type(svc):
    approve(svc,opportunity_packet('宁波政策传播招聘',typ='PUBLIC_INSTITUTION_JOB',region='宁波',summary='负责青年政策宣传',unit_name='政策宣传岗'),'sg5-infer-job')
    approve(svc,opportunity_packet('宁波一次性求职补贴',typ='YOUTH_POLICY_BENEFIT',region='宁波',summary='毕业生求职补贴',unit_name='一次性求职补贴'),'sg5-infer-policy')
    svc.set_profile({'cities':['宁波'],'interests':['政策'],'personalization_enabled':True},actor='reader')
    r=svc.recommendations(actor='reader',limit=2)
    assert r['items'][0]['type']=='YOUTH_POLICY_BENEFIT'
    assert r['items'][0]['title']=='一次性求职补贴'
    assert 'YOUTH_POLICY_BENEFIT' in r['inferred_opportunity_types']

def test_high_qualification_risk_uncertain_stays_visible_but_not_featured(svc):
    risky=approve(svc,opportunity_packet(
        '宁波事业单位计算机重点岗',typ='PUBLIC_INSTITUTION_JOB',region='宁波',
        summary='计算机事业单位重点岗位',unit_name='计算机重点岗',
        facts=[fact('学历','硕士研究生以上')],
    ),'sg6-2-risky-uncertain')
    safe=approve(svc,opportunity_packet(
        '宁波事业单位综合服务岗',typ='PUBLIC_INSTITUTION_JOB',region='宁波',
        summary='事业单位综合服务岗位',unit_name='综合服务岗',
    ),'sg6-2-safe-uncertain')
    svc.set_profile({
        'education':'专科','major':'计算机','cities':['宁波'],
        'opportunity_types':['PUBLIC_INSTITUTION_JOB'],'career_directions':['计算机'],
        'personalization_enabled':True,
    },actor='reader')
    result=svc.recommendations(actor='reader',limit=10)
    by_id={x['id']:x for x in result['items']}
    assert risky in by_id, 'Evidence不足时不能把官方UNCERTAIN机会从探索列表硬删除'
    assert by_id[risky]['eligibility_status']=='UNCERTAIN'
    assert by_id[risky]['qualification_gate']=='HOLD_FOR_CONFIRMATION'
    assert risky not in {x['id'] for x in result['featured']}, '明显资格冲突线索不能占据Top3'
    assert safe in {x['id'] for x in result['featured']}
