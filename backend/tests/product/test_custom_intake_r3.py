from .test_api import client,login
from .test_contract import svc
from .test_services_r3 import published,P


def test_custom_order_and_source_enter_review_in_one_atomic_submission(client):
    p=published(client,'custom');login(client,'reader')
    data={'code':'custom','version':p['version'],'key':'combined-custom-request','note':'希望关注公开科研助理的机会','site_name':'研究院栏目','site_url':'https://research.example.org/','consent':True}
    r=client.post(P+'/custom-requests',json=data);assert r.status_code==200,r.text
    assert r.json()['order']['state']=='REQUESTED' and r.json()['submission']['lead']['state']=='PENDING'
    assert client.post(P+'/custom-requests',json=data).json()==r.json()
    assert len(client.get(P+'/orders').json())==1 and len(client.get(P+'/submissions').json())==1
    login(client,'reviewer');assert len(client.get(P+'/review/leads').json())==1


def test_invalid_source_does_not_leave_half_order(client):
    p=published(client,'custom');login(client,'reader')
    data={'code':'custom','version':p['version'],'key':'combined-custom-request','note':'希望关注公开科研助理的机会','site_name':'研究院栏目','site_url':'http://127.0.0.1/','consent':True}
    assert client.post(P+'/custom-requests',json=data).status_code==400
    assert client.get(P+'/orders').json()==[]
    data['site_url']='https://research.example.org/';data['consent']=False
    assert client.post(P+'/custom-requests',json=data).status_code==400
    assert client.get(P+'/orders').json()==[]
