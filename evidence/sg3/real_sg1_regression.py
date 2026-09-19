from pathlib import Path
import hashlib,json,shutil,sqlite3,zipfile
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.upgrade import upgrade_actionable_catalog
from deepaha.product.models import CatalogTarget,OpportunityUnit
from sqlalchemy import select,func

SRC=Path('/mnt/data/deepaha-data.zip'); WORK=Path('/mnt/data/sg3_real_regression')
if WORK.exists():shutil.rmtree(WORK)
WORK.mkdir(parents=True)
with zipfile.ZipFile(SRC) as z:z.extractall(WORK)
data=WORK/'deepaha-data';db=data/'deepaha.db';objects=data/'objects'
legacy_tables=['opportunities','product_opportunity_identity','product_overview_publications','product_overview_decisions','product_tasks','product_overview_revisions']

def table_digest(path,table):
 c=sqlite3.connect(path);c.row_factory=sqlite3.Row
 rows=[dict(r) for r in c.execute(f'SELECT * FROM {table} ORDER BY 1')];c.close()
 blob=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode();return hashlib.sha256(blob).hexdigest(),len(rows)
def object_digest(root):
 rows=[]
 for p in root.rglob('*'):
  if p.is_file() and '.locks' not in p.parts:
   rows.append((str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()))
 return hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest(),len(rows)
before={t:table_digest(db,t) for t in legacy_tables};obj_before=object_digest(objects)
p=Product('sqlite:///'+str(db),objects)
result=upgrade_actionable_catalog(p,data/'backups'/'sg3-real-before-sg1.zip')
with p.db.tx(False) as s:
 total=s.scalar(select(func.count()).select_from(CatalogTarget)) or 0
 active=s.scalar(select(func.count()).select_from(CatalogTarget).where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))) or 0
 kinds=dict(s.execute(select(OpportunityUnit.kind,func.count()).group_by(OpportunityUnit.kind)).all())
after={t:table_digest(db,t) for t in legacy_tables};obj_after=object_digest(objects)
assert before==after,(before,after)
assert obj_before==obj_after,(obj_before,obj_after)
assert active==106 and kinds.get('GROUP')==58 and kinds.get('POSITION')==106,(active,kinds)
page=p.catalog(limit=50);assert page['total']==106
second=upgrade_actionable_catalog(p,data/'backups'/'sg3-real-repeat.zip');assert second['already_current'] and not second['data_modified']
out={'upgrade':result,'second_upgrade':second,'catalog_total':page['total'],'target_rows':total,'active_targets':active,'unit_kinds':kinds,'legacy_tables_unchanged':True,'objects_unchanged':True,'legacy_table_digests':after,'object_digest':obj_after}
(ROOT/'evidence/sg3/real_sg1_regression.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2,default=str))
