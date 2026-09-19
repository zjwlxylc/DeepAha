from datetime import date, timedelta

from .test_contract import svc
from .test_eligibility import hard_fact
import io, json, zipfile


def _zip(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,value in files.items(): z.writestr(name,value)
    return out.getvalue()


def _unique_packet(case_key, *, facts, coverage='COMPLETE', deadline=None, text_lines=None):
    official=f'https://research.example.org/notices/oracle-{case_key.lower()}'
    root={
      'opportunity_name':f'Oracle {case_key}', 'publish_unit':'SG7 Gold Oracle',
      'opportunity_type':'PUBLIC_INSTITUTION_JOB','official_url':official,
      'metadata':{'qualification_coverage':coverage},
      'announcement_level':[],
      'units':[{'id':f'g-{case_key}','name':f'单位-{case_key}','positions':[{'id':f'p-{case_key}','name':f'岗位-{case_key}','code':case_key,'facts':facts}]}],
    }
    if deadline:
        root['registration_deadline']=deadline
        root['announcement_level'].append({'field':'报名截止','value':deadline,'status':'CONFIRMED','evidence':[{'artifact_id':'a1','quote':'报名截止：'+deadline,'locator':{'line':1}}]})
    lines=list(text_lines or [])
    if deadline: lines.insert(0,'报名截止：'+deadline)
    return _zip({
      'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),
      'evidence.json':json.dumps({'artifacts':[{'artifact_id':'a1','local_path':'artifacts/notice.txt','url':official}]},ensure_ascii=False).encode(),
      'report.md':f'# {case_key}'.encode(),
      'artifacts/notice.txt':('\n'.join(lines)+'\n').encode(),
    })


def _approve_unique(svc, case_key, **kwargs):
    preview=svc.ingest(svc.test_source,_unique_packet(case_key,**kwargs),actor='operator')
    assert preview['can_approve']
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'',f'oracle-{case_key}',actor='reviewer')
    rows=svc.catalog(q=f'岗位-{case_key}',limit=20)['items']
    assert len(rows)==1, rows
    return rows[0]['id']


def _rank(education: str) -> int:
    return {'专科': 1, '本科': 2, '硕士研究生': 3}.get(education or '', 0)


def _oracle(case_key: str, profile: dict) -> str:
    """Independent deterministic oracle.

    This function must not import/call product eligibility/value code. Expected
    answers are derived solely from the frozen fixture specification and the
    twin profile fields.
    """
    if case_key == 'BACHELOR_MIN':
        return 'ELIGIBLE' if _rank(profile.get('education')) >= 2 else 'INELIGIBLE'
    if case_key == 'MASTER_MIN':
        return 'ELIGIBLE' if _rank(profile.get('education')) >= 3 else 'INELIGIBLE'
    if case_key == 'BACHELOR_2027':
        return 'ELIGIBLE' if (_rank(profile.get('education')) >= 2 and profile.get('graduation_year') == 2027) else 'INELIGIBLE'
    if case_key == 'EXPIRED':
        return 'INELIGIBLE'
    if case_key == 'MISSING_MAJOR_CODE':
        # Gold opportunity requires explicit 07/08 major code family. SG7 twins
        # deliberately have blank major_code; safe standard answer is UNKNOWN.
        return 'UNCERTAIN'
    if case_key == 'EXCEPTION_LANGUAGE':
        # "硕士及以上；高级职称可放宽" contains an explicit exception.
        # Without validating the exception branch, hard denial is unsafe.
        return 'UNCERTAIN'
    raise AssertionError(case_key)


def test_sg7_100_twins_against_independent_deterministic_gold_oracle(svc):
    svc.lab_seed_twins(actor='operator')
    twins = svc.lab_twins(actor='operator', limit=100)['items']
    assert len(twins) == 100

    future = (date.today() + timedelta(days=90)).isoformat()
    past = (date.today() - timedelta(days=5)).isoformat()

    fixtures = [
        ('BACHELOR_MIN', _approve_unique(svc, 'BACHELOR_MIN',
            facts=[hard_fact('学历','本科及以上','学历：本科及以上')],
            deadline=future, text_lines=['学历：本科及以上'])),
        ('MASTER_MIN', _approve_unique(svc, 'MASTER_MIN',
            facts=[hard_fact('学历','硕士研究生以上','学历：硕士研究生以上')],
            deadline=future, text_lines=['学历：硕士研究生以上'])),
        ('BACHELOR_2027', _approve_unique(svc, 'BACHELOR_2027',
            facts=[hard_fact('学历','本科及以上','学历：本科及以上'), hard_fact('毕业届别','2027届毕业生','届别：2027届毕业生')],
            deadline=future, text_lines=['学历：本科及以上','届别：2027届毕业生'])),
        ('EXPIRED', _approve_unique(svc, 'EXPIRED', facts=[], deadline=past)),
        ('MISSING_MAJOR_CODE', _approve_unique(svc, 'MISSING_MAJOR_CODE',
            facts=[hard_fact('专业','理学（07）、工学（08）','专业：理学（07）、工学（08）')],
            deadline=future, text_lines=['专业：理学（07）、工学（08）'])),
        ('EXCEPTION_LANGUAGE', _approve_unique(svc, 'EXCEPTION_LANGUAGE',
            facts=[hard_fact('学历','硕士研究生以上；具有高级职称者可放宽','学历：硕士研究生以上；具有高级职称者可放宽')],
            deadline=future, text_lines=['学历：硕士研究生以上；具有高级职称者可放宽'])),
    ]

    expected_counts = {}
    for case_key, target_id in fixtures:
        case = svc.lab_add_gold_case(
            target_id, actor='operator', split='LOCKED_ACCEPTANCE',
            truth_origin='ENGINEERING_FIXTURE',
            annotation={
                'oracle': 'independent_deterministic_v1',
                'case_key': case_key,
                'rule': 'predefined fixture specification; no product evaluator used',
            },
            lock=True,
        )
        counts = {}
        for twin in twins:
            expected = _oracle(case_key, twin['profile'])
            counts[expected] = counts.get(expected, 0) + 1
            svc.lab_set_pair_truth(
                case['id'], twin['key'], expected,
                actor='operator', truth_origin='ENGINEERING_FIXTURE',
                note=f'independent_deterministic_v1:{case_key}',
            )
        expected_counts[case_key] = counts

    run = svc.lab_run_benchmark(
        actor='operator', kind='GOLD_BENCHMARK', max_targets=len(fixtures),
        label='100 twins independent deterministic oracle v1',
    )
    metrics = run['metrics']
    assert metrics['pairs'] == 600
    assert metrics['truth_pairs'] == 600
    assert metrics['truth_origin_pairs'] == {'ENGINEERING_FIXTURE': 600}
    assert metrics['real_gold_pairs'] == 0
    assert metrics['llm_used'] is False
    assert metrics['production_mutated'] is False
    # The actual acceptance criterion: every product answer must match the
    # pre-frozen independent oracle answer for all six cases × all 100 twins.
    assert metrics['truth_accuracy'] == 1.0, metrics
    assert metrics['unsafe_recommendations'] == 0, metrics
    print('ORACLE_EXPECTED_COUNTS=', expected_counts)
    print('ORACLE_METRICS=', metrics)

    # Freeze the oracle distribution so accidental twin/oracle drift is caught.
    assert expected_counts == {
        'BACHELOR_MIN': {'INELIGIBLE': 25, 'ELIGIBLE': 75},
        'MASTER_MIN': {'INELIGIBLE': 75, 'ELIGIBLE': 25},
        'BACHELOR_2027': {'INELIGIBLE': 79, 'ELIGIBLE': 21},
        'EXPIRED': {'INELIGIBLE': 100},
        'MISSING_MAJOR_CODE': {'UNCERTAIN': 100},
        'EXCEPTION_LANGUAGE': {'UNCERTAIN': 100},
    }
