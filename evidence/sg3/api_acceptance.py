from pathlib import Path
import json,tempfile,sys
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.api import create_app
from deepaha.product.config import Settings
from deepaha.product.models import TargetNotice
from sqlalchemy import select
EX=ROOT/'examples/sg3-currentness';OUT=ROOT/'evidence/sg3'

def login(c,name='admin'):
 r=c.post('/api/auth/login',json={'username':name,'password':'long-password-123'});assert r.status_code==200,r.text
 c.headers['X-CSRF-Token']=r.json()['csrf']

def main():
 with tempfile.TemporaryDirectory(prefix='sg3-api-') as td:
  td=Path(td);p=Product('sqlite:///'+str(td/'app.db'),td/'objects');p.initialize()
  p.create_account('admin','long-password-123',['user','reviewer','operator'])
  source=p.add_source('海湾研究中心（虚构）','https://research.example.org/',actor='admin')
  app=create_app(Settings(database_url=p.database_url,data_dir=td,public_catalog=True,allowed_hosts=['testserver']),product=p)
  calls=[]
  with TestClient(app) as c:
   login(c)
   first=c.post('/api/intake/'+source['id'],content=(EX/'01_initial.zip').read_bytes(),headers={'Content-Type':'application/zip'});assert first.status_code==200,first.text;first=first.json()
   r=c.post('/api/review/'+first['id']+'/decision',json={'decision':'APPROVE','preview_hash':first['preview_hash'],'note':'','request_key':'sg3-api-v1'});assert r.status_code==200,r.text
   catalog=c.get('/api/catalog?limit=50').json();ids={x['code']:x['id'] for x in catalog['items']};assert set(ids)=={'A01','A02'}
   for code in ('A01','A02'):
    assert c.put('/api/me/actions/'+ids[code],json={'status':'SAVED','note':''}).status_code==200
    assert c.post('/api/me/reminders/'+ids[code],json={'days_before':1}).status_code==200
   pending=c.post('/api/intake/'+source['id'],content=(EX/'02_deadline_extension_A01.zip').read_bytes(),headers={'Content-Type':'application/zip'});assert pending.status_code==200,pending.text;pending=pending.json()
   review=c.get('/api/review/'+pending['id']).json();cur=review['opportunities'][0]['currentness']
   assert cur['counts']=={'changed':1,'added':0,'missing':0,'withdrawn':0,'unchanged':1}
   a01=c.get('/api/catalog/'+ids['A01']).json();a02=c.get('/api/catalog/'+ids['A02']).json()
   assert a01['status']=='UPDATE_PENDING' and a01['deadline'] is None
   assert a02['status']=='CURRENT' and a02['deadline']=='2026-11-20'
   with p.db.tx(False) as s:
    ns={n.target_public_id:n.state for n in s.scalars(select(TargetNotice).where(TargetNotice.kind=='DEADLINE'))}
   assert ns[ids['A01']]=='CANCELLED' and ns[ids['A02']]!='CANCELLED'
   recheck=c.post('/api/manage/catalog/'+ids['A01']+'/recheck',json={'request_key':'sg3-api-recheck','budget_seconds':1200});assert recheck.status_code==200,recheck.text
   assert recheck.json()['kind']=='RECHECK' and ids['A01'] in recheck.json()['instruction'] and 'A02' not in recheck.json()['instruction']
   approved=c.post('/api/review/'+pending['id']+'/decision',json={'decision':'APPROVE','preview_hash':pending['preview_hash'],'note':'','request_key':'sg3-api-v2'});assert approved.status_code==200,approved.text
   a01new=c.get('/api/catalog/'+ids['A01']).json();assert a01new['status']=='CURRENT' and a01new['deadline']=='2026-12-05'
   history=c.get('/api/catalog/'+ids['A01']+'/history').json();assert len(history['versions'])>=2
   cmp=c.get('/api/catalog/'+ids['A01']+'/compare',params={'from_id':history['versions'][1]['catalog_target_id'],'to_id':history['versions'][0]['catalog_target_id']}).json()
   assert cmp['changes']['deadline']=={'before':'2026-11-10','after':'2026-12-05'}
   # Explicit target withdrawal stays target-scoped.
   w=c.post('/api/catalog/'+ids['A01']+'/withdraw',json={'reason':'SG3验收：此具体岗位明确撤回'});assert w.status_code==200,w.text
   final=c.get('/api/catalog?limit=50').json();assert final['total']==1 and final['items'][0]['code']=='A02'
   for label,res in [('first_intake',first),('pending_review',cur),('recheck_task',recheck.json()),('history',history),('compare',cmp),('withdraw',w.json())]:calls.append({'step':label,'result':res})
  out={'result':'PASS','checks':['precise_unit_invalidation','sibling_unchanged','old_deadline_reminder_cancelled_only_for_affected_target','targeted_recheck','accepted_extension','history_compare','target_scoped_withdrawal'],'A01':ids['A01'],'A02':ids['A02'],'evidence':calls}
  (OUT/'api_acceptance.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
  print(json.dumps(out,ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()
