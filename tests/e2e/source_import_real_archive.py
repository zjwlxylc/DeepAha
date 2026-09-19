"""Offline compatibility replay of a user-selected research ZIP.
Uses original v0.3.1 Workspace.export and an isolated temporary main-system DB.
It does not approve real sources or call WMA. Never points at the user's DB.
"""
import argparse,json,sys,tempfile,hashlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend/src'),str(ROOT/'tools/source_asset_importer')]
from deepaha.product.service import Product
from deepaha_importer.research.workspace import Workspace


def main():
 ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 if a.archive.stat().st_size>100*1024*1024:raise SystemExit('Archive exceeds 100MiB')
 start=time.monotonic()
 with tempfile.TemporaryDirectory(prefix='deepaha-scout-replay-') as td:
  root=Path(td);w=Workspace(root/'tool');x=w.create([a.archive]);out=w.export(x['id'],x['revision']);raw=Path(out['path']).read_bytes()
  svc=Product('sqlite:///'+str(root/'main.db'),root/'objects');svc.initialize();svc.create_account('integration-test','test-only-long-password',['operator'])
  p=svc.scout_prepare(raw,Path(out['path']).name,actor='integration-test');assert p['status']=='PREPARED',p
  rows=[];off=0
  while True:
   page=svc.scout_items(p['id'],actor='integration-test',offset=off,limit=50);rows.extend(page['items']);off+=50
   if off>=page['total']:break
  ids=[g['id'] for g in rows if not g['blocking']]
  r=svc.scout_commit(p['id'],p['preview_hash'],ids,'isolated-replay',actor='integration-test')
  again=Product(svc.database_url,svc.object_root);again.initialize();assert again.scout_receipt(p['id'],actor='integration-test')==r
  assert svc.list_sources(actor='integration-test')==[] and svc.tasks(actor='integration-test')==[]
  fb=svc.scout_feedback(p['id'],actor='integration-test');raw_fb=json.dumps(fb,ensure_ascii=False).encode();x=w.add_feedback(x['id'],raw_fb,x['revision'])
  inspection=x['feedback'][0]['verification'];assert inspection['bundle_binding']=='MATCH'
  result={'input_filename':a.archive.name,'input_sha256':hashlib.sha256(a.archive.read_bytes()).hexdigest(),
   'tool_version':'0.3.1','summary':p['summary'],'export_readiness':p['readiness'],
   'server_received_candidates':r['received'],'not_selected':r['not_selected'],'sources_created':0,'tasks_created':0,'opportunities_created':0,
   'original_tool_feedback_inspection':inspection,'restart_receipt_equal':True,'elapsed_seconds':round(time.monotonic()-start,3),
   'database':'ISOLATED_TEMPORARY_SQLITE','technical_replay_not_human_approval':True,'network_calls':0}
  svc.db.engine.dispose();again.db.engine.dispose()
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
