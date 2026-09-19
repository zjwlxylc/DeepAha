from pathlib import Path
import subprocess, os, signal, json, re, sys
root=Path(__file__).resolve().parents[2]
backend=root/'backend'
files=sorted((backend/'tests/product').glob('test_*.py'))
results=[]
for f in files:
    log=root/'evidence/sg6_1'/('pytest_'+f.stem+'.log')
    with log.open('wb') as out:
        p=subprocess.Popen([sys.executable,'-m','pytest',str(f.relative_to(backend)),'-o','addopts=','-q'],cwd=backend,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            rc=p.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL); p.wait(); rc=124
    text=log.read_text(errors='replace')
    m=re.findall(r'(\d+) passed',text)
    results.append({'file':f.name,'rc':rc,'passed':int(m[-1]) if m else 0,'tail':'\n'.join(text.splitlines()[-3:])})
    print(f'{f.name}: RC={rc} passed={results[-1]["passed"]}',flush=True)
    if rc != 0:
        break
summary={'files':len(results),'passed':sum(x['passed'] for x in results),'failed_files':[x for x in results if x['rc']!=0],'results':results}
(root/'evidence/sg6_1/product_tests_final.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'files':summary['files'],'passed':summary['passed'],'failed_file_count':len(summary['failed_files'])},ensure_ascii=False))
sys.exit(1 if summary['failed_files'] else 0)
