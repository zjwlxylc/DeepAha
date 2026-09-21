#!/usr/bin/env python3
"""R2 local product verification; no production DB or remote Agent calls."""
import argparse,json,os,subprocess,sys,time,shutil
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPAHA_','WMA_'))};env.update(PYTHONPATH=str(ROOT/'backend/src'),PYTHONUTF8='1')
    stages=[]
    def run(name,cmd,cwd=ROOT):
        started=time.monotonic()
        with (out/(name+'.log')).open('w',encoding='utf-8') as log:
            try:r=subprocess.run(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900);code=r.returncode
            except (OSError,subprocess.TimeoutExpired) as error:log.write(str(error));code=125
        stages.append({'name':name,'command':cmd,'returncode':code,'seconds':round(time.monotonic()-started,2)});print(name,code,flush=True)
    run('asset-build',[sys.executable,'scripts/mobile_r2/build_assets.py','--check'])
    # Explicitly resolve pyproject testpaths from the repository root (avoid historical CLI scripts).
    run('product-full',[sys.executable,'-m','pytest','-c','backend/pyproject.toml','backend/tests/product','--junitxml='+str(out/'product.xml')])
    run('compileall',[sys.executable,'-m','compileall','-q','backend/src','backend/tests/product','scripts/mobile_r2'])
    node=shutil.which('node') or 'node'
    for script in ['check-product','check-sg7-1','check-sg7-2','test-product-core','test-birth-date','test-experience','test-mobile-r2','test-mobile-r2-ops']:
        run(script,[node,'scripts/'+script+'.mjs'],ROOT/'web')
    run('http-smoke',[sys.executable,'scripts/mobile_r2/http_smoke.py','--output',str(out/'http')])
    counts={}
    if (out/'product.xml').exists():
        root=ET.parse(out/'product.xml').getroot();suites=list(root.iter('testsuite'));counts={k:sum(int(x.get(k,'0')) for x in suites) for k in ('tests','failures','errors','skipped')};counts['passed']=counts['tests']-counts['failures']-counts['errors']-counts['skipped']
    result={'status':'PASS' if all(x['returncode']==0 for x in stages) else 'FAIL','stages':stages,'counts':counts,'wma_called':False,'postgres_live':'NOT_RUN','physical_mobile':'NOT_RUN','native_windows':'NOT_RUN','new_schema_tables':0}
    (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
