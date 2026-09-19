import argparse, hashlib, json, sqlite3
from collections import Counter
from pathlib import Path
from deepaha.product.service import Product


def file_tree_digest(root: Path):
    h=hashlib.sha256(); count=0; size=0
    for p in sorted(x for x in root.rglob('*') if x.is_file()):
        rel=p.relative_to(root).as_posix().encode(); data=p.read_bytes()
        h.update(rel+b'\0'+hashlib.sha256(data).digest()); count+=1; size+=len(data)
    return {'files':count,'bytes':size,'tree_sha256':h.hexdigest()}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('data_dir'); ap.add_argument('--out',default='evidence/sg5/real_wma_value_replay.json')
    a=ap.parse_args(); root=Path(a.data_dir); db=root/'deepaha.db'
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    schema_before='\n'.join(r['sql'] or '' for r in con.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','index') ORDER BY name"))
    stats={t:con.execute(f'SELECT COUNT(*) c FROM {t}').fetchone()['c'] for t in [
      'product_tasks','product_result_snapshots','product_overview_revisions','product_overview_decisions',
      'product_overview_publications','product_opportunity_identity','product_opportunity_units','product_catalog_targets']}
    types=Counter()
    for r in con.execute('SELECT content FROM product_catalog_targets WHERE status="CURRENT"'):
        c=json.loads(r['content']) if isinstance(r['content'],str) else r['content']; types[c.get('type') or c.get('opportunity_type') or 'UNKNOWN']+=1
    task_states=[dict(r) for r in con.execute('SELECT status,stage,COUNT(*) count FROM product_tasks GROUP BY status,stage ORDER BY status,stage')]
    con.close()
    db_before=hashlib.sha256(db.read_bytes()).hexdigest(); objects_before=file_tree_digest(root/'objects')
    p=Product('sqlite:///'+str(db),root/'objects'); p.initialize()
    scenarios={
      'existing_minimal': {'cities':['宁波'],'interests':['政策'],'personalization_enabled':True},
      'explicit_policy': {'cities':['宁波'],'interests':['政策'],'goals':['获得求职支持'],'opportunity_types':['YOUTH_POLICY_BENEFIT'],'region_preference_mode':'PREFERRED','personalization_enabled':True},
      'ai_competition': {'cities':['浙江'],'interests':['AI'],'goals':['积累项目经历'],'career_directions':['AI产品/技术'],'opportunity_types':['COMPETITION'],'region_preference_mode':'FLEXIBLE','personalization_enabled':True},
    }
    outs={}
    for name,profile in scenarios.items():
        p.set_profile(profile,actor='owner'); r=p.recommendations(actor='owner',limit=12)
        outs[name]={
          'basis':r['basis'],'llm_used':r['llm_used'],'candidate_count':r['candidate_count'],'evaluated_count':r['evaluated_count'],
          'excluded_ineligible':r['excluded_ineligible'],'inferred_opportunity_types':r.get('inferred_opportunity_types',[]),
          'featured':[{'title':x['title'],'type':x['type'],'priority_band':x['priority_band'],'eligibility_status':x['eligibility_status'],'why_for_you':x['why_for_you'],'why_now':x['why_now'],'risks':x['risks']} for x in r['featured']],
          'top12':[{'title':x['title'],'type':x['type'],'priority_band':x['priority_band'],'eligibility_status':x['eligibility_status']} for x in r['items'][:12]],
        }
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    schema_after='\n'.join(r['sql'] or '' for r in con.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','index') ORDER BY name")); con.close()
    out={
      'stats':stats,
      'target_type_counts':[{'type':k,'count':v} for k,v in types.most_common()],
      'task_status_stage_counts':task_states,
      'schema_unchanged_by_sg5_initialize': schema_before==schema_after,
      'database_sha256_before_profile_calibration':db_before,
      'objects_before':objects_before,
      'objects_after':file_tree_digest(root/'objects'),
      'objects_unchanged':objects_before==file_tree_digest(root/'objects'),
      'scenarios':outs,
    }
    Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
