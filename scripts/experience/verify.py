#!/usr/bin/env python3
"""Offline product regression. Never enables WMA. PostgreSQL tests are opt-in."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json,os,shutil,subprocess,sys,time
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]

def counts(path:Path)->dict:
    if not path.exists():return {}
    root=ET.parse(path).getroot();suites=[root] if root.tag=='testsuite' else list(root.findall('testsuite'))
    values={k:sum(int(x.get(k,'0')) for x in suites) for k in ('tests','failures','errors','skipped')}
    values['passed']=values['tests']-values['failures']-values['errors']-values['skipped'];return values

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--skip-per-file',action='store_true',help='Full suite still runs')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPAHA_WMA_','WMA_'))}
    env.update(PYTHONPATH=str(ROOT/'backend/src'),PYTHONUTF8='1')
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'base':'84353c7e5286e276d24af8e0342d4d3441c30ec5','wma_called':False,'stages':[]}
    def save():(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def run(label,cmd,cwd=ROOT,junit=None):
        start=time.monotonic()
        with (out/(label+'.log')).open('w',encoding='utf-8') as log:
            try:rc=subprocess.run(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600,check=False).returncode
            except (OSError,subprocess.TimeoutExpired) as ex:log.write(type(ex).__name__+': '+str(ex));rc=125
        entry={'name':label,'command':cmd,'returncode':rc,'seconds':round(time.monotonic()-start,2)}
        if junit:entry['counts']=counts(junit)
        result['stages'].append(entry);save();print(label,rc,entry.get('counts',''),flush=True)
    tests=sorted((ROOT/'backend/tests/product').glob('test_*.py'))
    if not tests:raise SystemExit('No product tests found')
    full=out/'product-full.xml'
    run('product-full',[sys.executable,'-m','pytest','-c','backend/pyproject.toml','backend/tests/product','--junitxml='+str(full)],junit=full)
    if not args.skip_per_file:
        for test in tests:
            junit=out/(test.stem+'.xml')
            run(test.stem,[sys.executable,'-m','pytest',str(test.relative_to(ROOT)),'-q','--junitxml='+str(junit)],junit=junit)
    run('compileall',[sys.executable,'-m','compileall','-q','backend/src','backend/tests/product','scripts/experience'])
    node=shutil.which('node') or 'node'
    for name in ('check-product','check-sg7-1','check-sg7-2','test-birth-date','test-product-core','test-experience'):
        run(name,[node,'scripts/'+name+'.mjs'],cwd=ROOT/'web')
    result.update(status='PASS' if all(x['returncode']==0 for x in result['stages']) else 'FAIL',
        postgres_scope='Dedicated PostgreSQL tests requested' if env.get('DEEPAHA_EXPERIENCE_TEST_POSTGRES_URL') else 'NOT_RUN; two opt-in tests skipped',
        native_windows_tested=False,human_acceptance='NOT_RUN',production_deployment='NOT_RUN')
    save();return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
