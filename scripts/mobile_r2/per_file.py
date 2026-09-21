#!/usr/bin/env python3
"""Re-run each current product test file in its own interpreter, isolated tmp dirs."""
import argparse,json,os,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPAHA_','WMA_'))};env.update(PYTHONPATH=str(ROOT/'backend/src'),PYTHONUTF8='1')
    def run(file):
        t=time.monotonic();cmd=[sys.executable,'-m','pytest','-c','backend/pyproject.toml',str(file.relative_to(ROOT)),'--junitxml='+str(out/(file.stem+'.xml'))]
        with (out/(file.stem+'.log')).open('w',encoding='utf-8') as log:
            try:code=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
            except (OSError,subprocess.TimeoutExpired) as error:log.write(str(error));code=125
        return {'file':file.name,'returncode':code,'seconds':round(time.monotonic()-t,2)}
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,sorted((ROOT/'backend/tests/product').glob('test_*.py'))))
    value={'status':'PASS' if all(x['returncode']==0 for x in results) else 'FAIL','files':results};(out/'per-file.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');print(value['status'],len(results),'test files');return int(value['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
