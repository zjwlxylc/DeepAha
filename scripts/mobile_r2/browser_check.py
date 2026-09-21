#!/usr/bin/env python3
"""Start an isolated synthetic API (NO worker) and run browser acceptance.
Default is native Chromium. --transport bridge is an explicitly limited fallback
for environments whose managed policy prohibits all native URL navigation.
"""
import argparse,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--transport',choices=['native','bridge'],default='native');ap.add_argument('--chromium',type=Path)
    ap.add_argument('--layout-only',action='store_true');ap.add_argument('--focused',action='store_true');ap.add_argument('--edges',action='store_true');args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='deepaha-browser-') as data:
        env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPAHA_','WMA_'))}
        env.update(DEEPAHA_QA_DATA=data,DEEPAHA_QA_PORT=str(port),DEEPAHA_QA_OUTPUT=str(out),DEEPAHA_QA_TRANSPORT=args.transport,PYTHONUTF8='1',PYTHONPATH=str(ROOT/'backend/src'))
        if args.layout_only:env['DEEPAHA_QA_LAYOUT_ONLY']='1'
        if args.chromium:env['DEEPAHA_QA_CHROMIUM']=str(args.chromium.resolve())
        with (out/'fixture-server.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([sys.executable,str(ROOT/'scripts/mobile_r2/fixture_server.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    if process.poll() is not None:raise RuntimeError('Synthetic API exited; see fixture-server.log')
                    try:
                        with opener.open(f'http://127.0.0.1:{port}/health/ready',timeout=1) as r:
                            if r.status==200:break
                    except OSError:time.sleep(.2)
                else:raise RuntimeError('Synthetic API not ready')
                with (out/'browser-check.log').open('w',encoding='utf-8') as report:
                    rc=subprocess.run([sys.executable,str(ROOT/'scripts/mobile_r2'/('focused_cases.py' if args.focused else 'edge_cases.py' if args.edges else 'browser_cases.py'))],cwd=ROOT,env=env,stdout=report,stderr=subprocess.STDOUT,timeout=600).returncode
                print('Browser scope:',args.transport,'; returncode:',rc,'; evidence:',out)
                return rc
            finally:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':raise SystemExit(main())
