from pathlib import Path
import hashlib,json,shutil,sqlite3,zipfile,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.upgrade import upgrade_actionable_catalog
from deepaha.product.models import CatalogTarget,OpportunityUnit
from sqlalchemy import select,func
SRC=Path('/mnt/data/deepaha-data.zip'); WORK=Path('/mnt/data/sg4_real_regression')
if WORK.exists():shutil.rmtree(WORK)
WORK.mkdir(parents=True)
with zipfile.ZipFile(SRC) as z:z.extractall(WORK)
data=WORK/'deepaha-data';db=data/'deepaha.db';objects=data/'objects'
legacy_tables=['opportunities','product_opportunity_identity','product_overview_publications','product_overview_decisions','product_tasks','product_overview_revisions']
def table_digest(path,table):
 c=sqlite3.connect(path);c.row_factory=sqlite3.Row;rows=[dict(r) for r in c.execute(f'SELECT * FROM {table} ORDER BY 1')];c.close();return hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest(),len(rows)
def object_digest(root):
 rows=[]
 for p in root.rglob('*'):
  if p.is_file() and '.locks' not in p.parts:rows.append((str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()))
 return hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest(),len(rows)
before={t:table_digest(db,t) for t in legacy_tables};obj_before=object_digest(objects)
p=Product('sqlite:///'+str(db),objects);upgrade=upgrade_actionable_catalog(p,data/'backups'/'sg4-real-before-sg1.zip')
with p.db.tx(False) as s:
 total=s.scalar(select(func.count()).select_from(CatalogTarget)) or 0;active=s.scalar(select(func.count()).select_from(CatalogTarget).where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))) or 0;kinds=dict(s.execute(select(OpportunityUnit.kind,func.count()).group_by(OpportunityUnit.kind)).all())
page=p.catalog(q='综合管理',limit=50); target=next(x for x in page['items'] if x.get('code')=='1')
p.set_profile({'education':'本科','major':'广告学','major_code':'050303','birth_date':'1985-01-01'},actor='owner')
fit=p.fit(target['id'],actor='owner')
after={t:table_digest(db,t) for t in legacy_tables};obj_after=object_digest(objects)
assert before==after and obj_before==obj_after
assert active==106 and kinds.get('GROUP')==58 and kinds.get('POSITION')==106
assert p.catalog(limit=50)['total']==106
assert fit['status']=='INELIGIBLE',fit
hard={x['type']:x for x in fit['hard_conflicts']}
assert 'EDUCATION_MIN' in hard and 'MAJOR_CODE_SET' in hard,hard
edu=next(x for x in fit['requirements'] if x['type']=='EDUCATION_MIN')
major=next(x for x in fit['requirements'] if x['type']=='MAJOR_CODE_SET')
assert edu['evidence_support']=='LOCATED' and any(x['verification']=='XLSX_CELL_MATCH' for x in edu['evidence'])
assert major['evidence_support']=='LOCATED' and any(x['verification']=='XLSX_CELL_MATCH' for x in major['evidence'])
second=upgrade_actionable_catalog(p,data/'backups'/'sg4-real-repeat.zip');assert second['already_current'] and not second['data_modified']
out={'result':'PASS','upgrade':upgrade,'second_upgrade':second,'catalog_total':106,'active_targets':active,'unit_kinds':kinds,'sample_target':{'id':target['id'],'title':target['title'],'code':target['code']},'profile':p.get_profile(actor='owner'),'fit_status':fit['status'],'hard_conflict_types':list(hard),'education_evidence':edu['evidence'],'major_evidence':major['evidence'],'legacy_tables_unchanged':True,'objects_unchanged':True}
(ROOT/'evidence/sg4/real_106_eligibility.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2,default=str))
