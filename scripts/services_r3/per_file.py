"""Independent interpreter per current product test file; no shared fixture state."""
import argparse,concurrent.futures,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=2);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPAHA_','WMA_'))};env['PYTHONPATH']=str(ROOT/'backend/src')
 def run(file):
  start=time.monotonic();command=[sys.executable,'-m','pytest',str(file),'-q']
  with (out/(file.stem+'.log')).open('w') as log:
   try:code=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
   except subprocess.TimeoutExpired:code=124
  item={'file':file.name,'returncode':code,'seconds':round(time.monotonic()-start,2)};print(item,flush=True);return item
 with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(a.jobs,4))) as pool:results=list(pool.map(run,sorted((ROOT/'backend/tests/product').glob('test_*.py'))))
 (out/'per-file.json').write_text(json.dumps(results,indent=2));return 0 if all(x['returncode']==0 for x in results) else 1
if __name__=='__main__':raise SystemExit(main())
