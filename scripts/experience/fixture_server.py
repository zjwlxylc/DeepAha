"""Synthetic QA only: .example.org sources, no worker, no external requests."""
import os,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'backend/src'))
sys.path.insert(0,str(REPO))
from deepaha.product.service import Product
from deepaha.product.config import Settings
from deepaha.product.api import create_app
from backend.tests.product.test_contract import packet
from deepaha.product.models import Task,now
from sqlalchemy import select
root=Path(os.environ['DEEPAHA_QA_DATA']).resolve();root.mkdir(exist_ok=True)
if (root/'browser.db').exists():raise SystemExit('QA requires a new empty data directory')
p=Product('sqlite:///'+str(root/'browser.db'),root/'objects');p.initialize()
for name,roles in [('owner',['operator']),('reader',['user']),('reviewer',['reviewer'])]:
 try:p.create_account(name,'test-browser-123',roles)
 except Exception:pass
for i in range(120):
 p.add_source(('第120号唯一目标来源' if i==119 else f'研究来源 {i+1:03}'),'https://source'+str(i)+'.example.org/',actor='owner')
s=p.add_source('海湾研究中心','https://research.example.org/',actor='owner')
pref=p.profile_state(actor='reader');p.patch_profile({'major':'广告学','certificates':['CET6'],'cities':['宁波'],'notification_enabled':False},pref['version'],actor='reader')
if not p.catalog()['total']:
 a=p.ingest(s['id'],packet(),actor='owner');p.decide(a['id'],'APPROVE',a['preview_hash'],'','browser-approve',actor='owner')
 t=p.catalog()['items'][0];p.set_action(t['id'],'SAVED',actor='reader',note='准备申请资料')
 p.ingest(s['id'],packet(title='待审核：青年科研实践项目（包含一般备注）'),actor='owner')
 p.ingest(s['id'],packet(title='来源不匹配返回',extra={'official_url':'https://unrelated.example.net/notice'}),actor='owner')
 p.create_task(s['id'],s['url'],actor='owner',request_key='browser-task',instruction='检查本栏目第一页公开公告和附件')
settings=Settings(data_dir=root,database_url=p.database_url,public_catalog=True,allow_registration=True,allowed_hosts=['127.0.0.1','localhost','testserver','fixture.deepaha.test'])
import uvicorn
uvicorn.run(create_app(settings,p),host='127.0.0.1',port=int(os.environ['DEEPAHA_QA_PORT']),log_level='warning')
