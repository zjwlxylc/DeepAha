from datetime import date, timedelta

from .test_contract import svc
from .test_personal_value import opportunity_packet


def _approve_case(svc, case_no: int, typ: str, region: str) -> str:
    title=f'Oracle推荐题{case_no:02d}'
    unit=f'标准机会-{case_no:02d}'
    blob=opportunity_packet(
        title, typ=typ, region=region, summary='标准测试机会',
        deadline=(date.today()+timedelta(days=90)).isoformat(), unit_name=unit,
    )
    preview=svc.ingest(svc.test_source,blob,actor='operator')
    assert preview['can_approve']
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'',f'rec-oracle-{case_no}',actor='reviewer')
    rows=svc.catalog(q=unit,limit=20)['items']
    assert len(rows)==1, rows
    return rows[0]['id']


def _oracle(profile: dict, typ: str, region: str) -> str:
    """Independent recommendation oracle from the published SG5 contract.

    1) Explicit opportunity type selections are a hard retrieval gate.
    2) STRICT region mode filters known region mismatches.
    3) FLEXIBLE/PREFERRED region mismatch is not a hard exclusion.
    4) The fixture is otherwise a safe, future, generic opportunity; an explicit
       type match is intentionally strong enough to be a headline candidate.
    No SG5 retrieval/value function is imported or called here.
    """
    selected=set(profile.get('opportunity_types') or [])
    if selected and typ not in selected:
        return 'HOLD'
    cities=profile.get('cities') or []
    if profile.get('region_preference_mode')=='STRICT' and cities and region not in cities:
        return 'HOLD'
    return 'FEATURE'


def test_sg7_100_twins_against_independent_recommendation_oracle(svc):
    svc.lab_seed_twins(actor='operator')
    twins=svc.lab_twins(actor='operator',limit=100)['items']
    assert len(twins)==100

    types=['STATE_OWNED_ENTERPRISE_JOB','PUBLIC_INSTITUTION_JOB','YOUTH_DEVELOPMENT_PROGRAM','COMPETITION','RESEARCH_PROGRAM','SCHOLARSHIP','POSTGRAD_RECOMMENDATION','YOUTH_POLICY_BENEFIT']
    cities=['杭州','宁波','上海','北京','深圳','广州','南京','武汉','成都','长沙']

    # 20 fixed cases: every city appears twice; opportunity types rotate.
    cases=[]
    for i in range(20):
        typ=types[(i*3)%len(types)]
        city=cities[i%len(cities)]
        target_id=_approve_case(svc,i+1,typ,city)
        gold=svc.lab_add_gold_case(
            target_id,actor='operator',split='LOCKED_ACCEPTANCE',truth_origin='ENGINEERING_FIXTURE',
            annotation={'oracle':'independent_preference_oracle_v1','case_no':i+1,'type':typ,'region':city,
                        'rule':'HOLD on explicit type mismatch or STRICT region mismatch; otherwise FEATURE for this safe generic fixture'},lock=True,
        )
        cases.append((gold,typ,city))

    expected={'FEATURE':0,'EXPLORE':0,'HOLD':0}
    for gold,typ,city in cases:
        for twin in twins:
            label=_oracle(twin['profile'],typ,city)
            expected[label]+=1
            svc.lab_set_pair_truth(
                gold['id'],twin['key'],actor='operator',expected_recommendation=label,
                truth_origin='ENGINEERING_FIXTURE',note='independent_preference_oracle_v1',
            )

    run=svc.lab_run_benchmark(actor='operator',kind='GOLD_BENCHMARK',max_targets=20,label='100 twins independent recommendation oracle v1')
    m=run['metrics']
    print('RECOMMENDATION_ORACLE_EXPECTED=',expected)
    print('RECOMMENDATION_ORACLE_METRICS=',m)
    assert m['pairs']==2000
    assert m['recommendation_truth_pairs']==2000
    assert m['recommendation_truth_origin_pairs']=={'ENGINEERING_FIXTURE':2000}
    assert m['llm_used'] is False and m['production_mutated'] is False
    from deepaha.product.models import LabRunResult
    from sqlalchemy import select
    with svc.db.tx(False) as db:
        rows=list(db.scalars(select(LabRunResult).where(LabRunResult.run_id==run['id'])))
    cm={}
    mismatches=[]
    for row in rows:
        actual=row.detail.get('recommendation_class')
        key=(row.expected_recommendation,actual)
        cm[key]=cm.get(key,0)+1
        if row.expected_recommendation!=actual and len(mismatches)<20:
            mismatches.append({'target':row.target_public_id,'expected':row.expected_recommendation,'actual':actual,'band':row.priority_band,'status':row.eligibility_status,'detail':row.detail})
    print('RECOMMENDATION_CONFUSION=',cm)
    print('RECOMMENDATION_MISMATCH_EXAMPLES=',mismatches)
    assert m['recommendation_accuracy']==1.0, m
    assert m['unsafe_recommendations']==0, m
