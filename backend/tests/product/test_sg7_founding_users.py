from .test_contract import svc
from .test_personal_value import approve, opportunity_packet


def test_founding_user_requires_explicit_join_and_records_only_after_consent(svc):
    target=approve(svc,opportunity_packet('SG7共创机会',region='宁波',summary='青年实践',unit_name='青年实践项目'),'sg7-founding')
    svc.set_profile({'cities':['宁波'],'personalization_enabled':True},actor='reader')
    assert svc.lab_me(actor='reader')['status']=='NOT_JOINED'
    svc.recommendations(actor='reader',limit=10)
    before=svc.lab_founding_metrics(actor='operator')
    assert before['active_participants']==0 and before['exposures']==0

    joined=svc.lab_join(actor='reader')
    assert joined['status']=='ACTIVE' and joined['external_model'] is False
    rec=svc.recommendations(actor='reader',limit=10)
    assert any(x['id']==target for x in rec['items'])
    svc.set_action(target,'SAVED',actor='reader')
    svc.feedback(target,{'previously_known':False,'useful':True,'action_reason':'原本不知道但值得行动','outcome':'APPLIED','comment':'这段自由文字不应出现在运营聚合'},actor='reader')
    metrics=svc.lab_founding_metrics(actor='operator')
    assert metrics['active_participants']==1
    assert metrics['exposures']>=1
    assert metrics['feedback_events']==1
    assert metrics['action_events']>=1
    assert metrics['previously_unknown_rate']==1.0
    assert metrics['useful_rate']==1.0
    assert metrics['free_text_returned'] is False
    assert 'reader' not in str(metrics)
    assert '这段自由文字' not in str(metrics)


def test_withdrawal_stops_future_lab_exposure_collection_without_breaking_normal_actions(svc):
    first=approve(svc,opportunity_packet('SG7退出前机会',region='宁波',unit_name='退出前'),'sg7-leave-1')
    svc.set_profile({'cities':['宁波'],'personalization_enabled':True},actor='reader')
    svc.lab_join(actor='reader');svc.recommendations(actor='reader',limit=50)
    old=svc.lab_me(actor='reader')['summary']['opportunities_observed']
    left=svc.lab_leave(actor='reader')
    assert left['status']=='WITHDRAWN'
    second=approve(svc,opportunity_packet('SG7退出后新机会',region='宁波',unit_name='退出后'),'sg7-leave-2')
    svc.recommendations(actor='reader',limit=50)
    current=svc.lab_me(actor='reader')['summary']['opportunities_observed']
    assert current==old
    svc.set_action(second,'SAVED',actor='reader')
    assert any(x['opportunity']['id']==second for x in svc.my_actions(actor='reader'))


def test_lab_consent_data_is_in_personal_export_and_erased_with_personal_data(svc):
    target=approve(svc,opportunity_packet('SG7隐私导出机会',region='宁波',unit_name='隐私导出'),'sg7-privacy')
    svc.set_profile({'cities':['宁波'],'personalization_enabled':True},actor='reader')
    svc.lab_join(actor='reader')
    svc.recommendations(actor='reader',limit=50)

    exported=svc.export_personal(actor='reader')
    lab=exported['opportunity_lab']
    assert lab['status']=='ACTIVE'
    assert lab['consent_version']=='sg7-opportunity-lab-v1'
    assert any(x['target_id']==target for x in lab['exposures'])

    assert svc.erase_personal(actor='reader')=={'erased':True}
    after=svc.export_personal(actor='reader')
    assert after['opportunity_lab']['status']=='NOT_JOINED'
    assert after['opportunity_lab']['exposures']==[]
    assert svc.lab_me(actor='reader')['status']=='NOT_JOINED'
