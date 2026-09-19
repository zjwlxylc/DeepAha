from sqlalchemy import func, select

from .test_contract import svc
from .test_personal_value import approve, opportunity_packet, fact


def test_sg7_seeds_exactly_100_versioned_synthetic_twins_idempotently(svc):
    first=svc.lab_seed_twins(actor='operator')
    second=svc.lab_seed_twins(actor='operator')
    assert first=={'created':100,'unchanged':0,'total':100,'synthetic_only':True,'version':2}
    assert second['created']==0 and second['unchanged']==100 and second['total']==100
    rows=svc.lab_twins(actor='operator',limit=100)
    assert rows['total']==100
    assert {x['key'] for x in rows['items']}=={f'TWIN-{i:03d}' for i in range(1,101)}
    assert all(x['synthetic'] is True and x['profile_hash'] and x['version']==2 for x in rows['items'])
    assert all(not x['profile'].get('display_name') for x in rows['items'])


def test_gold_opportunity_and_qualification_pair_truth_are_separate_and_do_not_mutate_production(svc):
    target_id=approve(svc,opportunity_packet(
        'SG7资格样本',typ='PUBLIC_INSTITUTION_JOB',region='宁波',unit_name='本科岗位',
        facts=[fact('学历','本科及以上','学历：本科及以上')],
    ),'sg7-case')
    svc.lab_seed_twins(actor='operator')
    from deepaha.product.models import Decision, Publication, CatalogTarget, LabPairTruth
    with svc.db.tx(False) as s:
        before={
            'decisions':s.scalar(select(func.count()).select_from(Decision)),
            'publications':s.scalar(select(func.count()).select_from(Publication)),
            'targets':s.scalar(select(func.count()).select_from(CatalogTarget)),
        }
    case=svc.lab_add_gold_case(target_id,actor='operator',split='CALIBRATION',truth_origin='OPERATOR_ANNOTATED',
        annotation={'note':'SG7本地工程标注，不是独立真人Gold'},lock=True)
    assert case['state']=='LOCKED'
    assert case['counts_as_real_gold'] is False
    truth=svc.lab_set_pair_truth(case['id'],'TWIN-001','INELIGIBLE',actor='operator',expected_recommendation='HOLD',truth_origin='OPERATOR_ANNOTATED',note='专科 vs 本科最低要求')
    assert truth['expected_eligibility']=='INELIGIBLE'
    assert truth['expected_recommendation']=='HOLD'
    assert truth['counts_as_real_gold'] is False
    assert len(svc.lab_pair_truths(case['id'],actor='operator'))==1

    run=svc.lab_run_benchmark(actor='operator',kind='GOLD_BENCHMARK',max_targets=1,label='pair truth separation')
    assert run['status']=='COMPLETED'
    assert run['metrics']['pairs']==100
    assert run['metrics']['truth_pairs']==1
    assert run['metrics']['truth_accuracy']==1.0
    assert run['metrics']['recommendation_truth_pairs']==1
    assert run['metrics']['recommendation_accuracy']==1.0
    assert run['metrics']['real_gold_pairs']==0
    assert run['metrics']['engineering_or_operator_pairs']==1
    assert run['metrics']['unsafe_recommendations']==0
    assert run['metrics']['production_mutated'] is False

    with svc.db.tx(False) as s:
        after={
            'decisions':s.scalar(select(func.count()).select_from(Decision)),
            'publications':s.scalar(select(func.count()).select_from(Publication)),
            'targets':s.scalar(select(func.count()).select_from(CatalogTarget)),
        }
        assert s.scalar(select(func.count()).select_from(LabPairTruth))==1
    assert after==before


def test_independent_human_gold_requires_attestation_and_is_counted_separately(svc):
    target_id=approve(svc,opportunity_packet('SG7人工Gold占位样本',unit_name='项目分项'),'sg7-human-gold')
    svc.lab_seed_twins(actor='operator')
    from deepaha.product.errors import Problem
    import pytest
    with pytest.raises(Problem) as exc:
        svc.lab_add_gold_case(target_id,actor='operator',truth_origin='INDEPENDENT_HUMAN_GOLD',lock=True)
    assert exc.value.code=='GOLD_ATTESTATION_REQUIRED'
    case=svc.lab_add_gold_case(target_id,actor='operator',truth_origin='INDEPENDENT_HUMAN_GOLD',attestation_ref='human-batch-001',lock=True)
    assert case['counts_as_real_gold'] is True
    with pytest.raises(Problem):
        svc.lab_set_pair_truth(case['id'],'TWIN-002','UNCERTAIN',actor='operator',truth_origin='INDEPENDENT_HUMAN_GOLD')
    pair=svc.lab_set_pair_truth(case['id'],'TWIN-002','UNCERTAIN',actor='operator',truth_origin='INDEPENDENT_HUMAN_GOLD',attestation_ref='human-pair-001')
    assert pair['counts_as_real_gold'] is True
    summary=svc.lab_summary(actor='operator')
    assert summary['real_gold']==1
    assert summary['real_qualification_pairs']==1


def test_catalog_safety_benchmark_preserves_sg6_2_headline_safety(svc):
    approve(svc,opportunity_packet(
        'SG7安全压力样本',typ='PUBLIC_INSTITUTION_JOB',region='宁波',unit_name='硕士岗位',
        # No located quote: SG4 must stay UNCERTAIN while SG5 may detect HIGH risk and hold headline.
        facts=[fact('学历','硕士研究生以上')],
    ),'sg7-safety')
    svc.lab_seed_twins(actor='operator')
    run=svc.lab_run_benchmark(actor='operator',kind='CATALOG_SAFETY',max_targets=10,label='safety')
    assert run['metrics']['pairs']>=100
    assert run['metrics']['unsafe_recommendations']==0
    assert run['metrics']['truth_pairs']==0
    assert run['metrics']['truth_accuracy'] is None
    assert run['metrics']['recommendation_truth_pairs']==0
    assert run['metrics']['recommendation_accuracy'] is None
    assert run['manifest']['production_mutation_allowed'] is False


def test_pair_truth_can_evaluate_recommendation_without_inventing_an_eligibility_truth(svc):
    target_id=approve(svc,opportunity_packet('SG7推荐真值样本',region='宁波',summary='青年实践项目',unit_name='青年实践项目'),'sg7-value-truth')
    svc.lab_seed_twins(actor='operator')
    case=svc.lab_add_gold_case(target_id,actor='operator',truth_origin='OPERATOR_ANNOTATED',lock=True)
    truth=svc.lab_set_pair_truth(case['id'],'TWIN-001',actor='operator',expected_recommendation='EXPLORE',truth_origin='OPERATOR_ANNOTATED')
    assert truth['expected_eligibility'] is None
    assert truth['expected_recommendation']=='EXPLORE'
    run=svc.lab_run_benchmark(actor='operator',kind='GOLD_BENCHMARK',max_targets=1,label='value-only truth')
    assert run['metrics']['truth_pairs']==0
    assert run['metrics']['recommendation_truth_pairs']==1
    assert run['metrics']['recommendation_accuracy'] in {0.0,1.0}
