import importlib
import pytest
from conftest import actor
from test_commerce import admin

class Product:
    def __init__(self):self.calls=[]
    def add_source(self,name,url,*,actor,brief,allowed_hosts,tier):
        self.calls.append(('source',name,url,actor,brief,tier));return {'id':'source1','enabled':False,'policy_version':2}
    def create_task(self,source_id,url,*,actor,request_key,instruction,kind,budget_seconds,connection_ref):
        self.calls.append(('task',source_id,url,actor,request_key,instruction,connection_ref));return {'id':'task1'}
    def source_status(self,id,enabled,reason,*,actor,expected_version):return {'id':id,'enabled':enabled}
    def task_detail(self,id,*,actor):return {'id':id,'status':'READY'}
    def catalog(self,**kwargs):return {'items':[],'total':0,'has_more':False,'read_version':1}

def port():
    try:C=importlib.import_module('deepaha_membership.integration').ProductPort
    except ImportError:pytest.fail('Product adapter missing')
    return C(Product(),None,connections=lambda:{'default':{}})

def lead():return dict(id='lead1',name='公开栏目',approved_url='https://example.org/jobs',tier='COMMUNITY_SIGNAL',public_brief='仅采集公开机会栏目，结果仍须审核',source_id='source1',note='SECRET USER NOTE')

def test_product_adapter_keeps_real_method_contract_and_not_raw_user_note():
    p=port();l=lead()
    assert p.register(admin(),l)['id']=='source1'
    assert p.enqueue(admin(),l,'mbr:job1','default')['id']=='task1'
    call=p.p.calls[-1]
    assert call[4]=='mbr:job1'
    assert 'SECRET' not in str(call)
    assert call[2]==l['approved_url']

def test_product_adapter_rejects_unknown_connection_before_call():
    p=port()
    with pytest.raises(Exception):p.enqueue(admin(),lead(),'mbr:job1','not-registered')
    assert p.p.calls==[]
