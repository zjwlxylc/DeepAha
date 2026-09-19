from pathlib import Path
import subprocess,re,json,sys,time
ROOT=Path(__file__).resolve().parents[2]
files=sorted((ROOT/'backend/tests/product').glob('test_*.py'))
results=[];total=0
for f in files:
    rel=str(f.relative_to(ROOT))
    started=time.time()
    cp=subprocess.run([sys.executable,'-m','pytest',rel,'-o','addopts=','-q'],cwd=ROOT,text=True,capture_output=True,timeout=120)
    text=(cp.stdout+cp.stderr).strip()
    matches=re.findall(r'(\d+) passed',text)
    passed=int(matches[-1]) if matches else 0
    total+=passed
    results.append({'file':rel,'exit_code':cp.returncode,'passed':passed,'seconds':round(time.time()-started,2),'output':text})
    print(f"{rel}: exit={cp.returncode} passed={passed}")
    if cp.returncode!=0:
        print(text);raise SystemExit(cp.returncode)
out={'result':'PASS','files':len(results),'passed':total,'failed':0,'results':results}
(ROOT/'evidence/sg4/product_tests_by_file.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'evidence/sg4/product_tests_by_file.txt').write_text('\n\n'.join(f"## {x['file']}\nexit={x['exit_code']} passed={x['passed']} seconds={x['seconds']}\n{x['output']}" for x in results),encoding='utf-8')
print(json.dumps({'result':'PASS','files':len(results),'passed':total,'failed':0},ensure_ascii=False))
