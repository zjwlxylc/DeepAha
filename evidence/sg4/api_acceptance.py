from pathlib import Path
import json,tempfile,sys
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.api import create_app
from deepaha.product.config import Settings
EX=ROOT/'examples/sg4-eligibility';OUT=ROOT/'evidence/sg4'

def login(c,name='admin'):
 r=c.post('/api/auth/login',json={'username':name,'password':'long-password-123'});assert r.status_code==200,r.text;c.headers['X-CSRF-Token']=r.json()['csrf']

def main():
 with tempfile.TemporaryDirectory(prefix='sg4-api-') as td:
  td=Path(td);p=Product('sqlite:///'+str(td/'app.db'),td/'objects');p.initialize();p.create_account('admin','long-password-123',['user','reviewer','operator'])
  src=p.add_source('海湾研究中心（虚构）','https://research.example.org/',actor='admin')
  app=create_app(Settings(database_url=p.database_url,data_dir=td,public_catalog=True,allowed_hosts=['testserver']),product=p)
  with TestClient(app) as c:
   login(c)
   for i,name in enumerate(['01_eligible_complete.zip','02_ineligible_xlsx.zip','03_uncertain_exception.zip','04_likely_bounded.zip'],1):
    r=c.post('/api/intake/'+src['id'],content=(EX/name).read_bytes(),headers={'Content-Type':'application/zip'});assert r.status_code==200,r.text;preview=r.json()
    r=c.post('/api/review/'+preview['id']+'/decision',json={'decision':'APPROVE','preview_hash':preview['preview_hash'],'note':'','request_key':f'sg4-example-{i}'});assert r.status_code==200,r.text
   profile={'education':'本科','major':'广告学','major_code':'050303','graduation_year':2027,'birth_date':'2004-06-01','hukou_region':'浙江省宁波市','cities':[],'interests':[],'goals':[],'skills':[],'notification_enabled':True}
   r=c.put('/api/me/profile',json=profile);assert r.status_code==200,r.text
   cat=c.get('/api/catalog?limit=50').json();assert cat['total']==4,cat
   by_code={x['code']:x for x in cat['items']}
   expected={'E01':'ELIGIBLE','I01':'INELIGIBLE','U01':'UNCERTAIN','L01':'LIKELY_ELIGIBLE'};fits={}
   for code,status in expected.items():
    r=c.get('/api/me/fit/'+by_code[code]['id']);assert r.status_code==200,r.text;fit=r.json();assert fit['status']==status,(code,fit);assert fit['llm_used'] is False;assert fit['decision_basis']=='DETERMINISTIC_EVIDENCE_BACKED';fits[code]=fit
   i01=fits['I01'];assert {x['type'] for x in i01['hard_conflicts']}=={'EDUCATION_MIN','MAJOR_CODE_SET'}
   assert all(any(ev['located'] for ev in x['evidence']) for x in i01['hard_conflicts'])
   exported=c.get('/api/me/export');assert exported.status_code==200;data=exported.json();assert data['profile']['major_code']=='050303' and data['profile']['birth_date']=='2004-06-01'
   out={'result':'PASS','catalog_total':4,'expected_statuses':expected,'actual_statuses':{k:v['status'] for k,v in fits.items()},'xlsx_conflict_types':[x['type'] for x in i01['hard_conflicts']],'llm_used':False,'profile_export_roundtrip':True}
  (OUT/'api_acceptance.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
