"""Offline Linux launcher lifecycle check using verified installed dependencies.
This is not a fresh pip installation, Windows execution, or production test.
"""
import hashlib,json,os,subprocess,sys,tempfile,time,urllib.request,venv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
VENV=ROOT/'.venv-product'

def main():
    if os.name=='nt':raise SystemExit('This harness was designed for the delivered Linux validation.')
    if not VENV.exists():venv.EnvBuilder(with_pip=False,system_site_packages=True).create(VENV)
    import site
    package_dir=next((VENV/'lib').glob('python*/site-packages'))
    (package_dir/'validation-dependencies.pth').write_text('\n'.join(site.getsitepackages())+'\n')
    python=VENV/'bin/python'
    code="""import importlib.metadata as m
from pathlib import Path
for line in Path('backend/requirements-product.txt').read_text().splitlines():
 if not line.strip() or line.startswith('#'):continue
 name,version=line.split('==');assert m.version(name)==version,(name,m.version(name),version)
"""
    subprocess.run([str(python),'-c',code],cwd=ROOT,check=True)
    (VENV/'.requirements-hash').write_text(hashlib.sha256((ROOT/'backend/requirements-product.txt').read_bytes()).hexdigest())
    with tempfile.TemporaryDirectory(prefix='deepaha-launcher-') as directory:
        env={**os.environ,'DEEPAHA_DATA_DIR':directory,'PYTHONPATH':str(ROOT/'backend/src'),'LOCAL_TEST_PASS':'Isolated-launcher-12345'}
        base=[str(python),'-m','deepaha.product.cli']
        subprocess.run(base+['init'],cwd=ROOT/'backend',env=env,check=True,capture_output=True)
        subprocess.run(base+['user-add','owner','--roles','user,reviewer,operator','--password-env','LOCAL_TEST_PASS'],cwd=ROOT/'backend',env=env,check=True,capture_output=True)
        process=subprocess.Popen([str(python),'scripts/launch_product.py','--no-browser','--port','8011'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8011/health/ready',timeout=.5) as response:
                        if response.status==200:break
                except OSError:time.sleep(.1)
            else:raise AssertionError('launcher did not become ready')
            status=subprocess.run([str(python),'scripts/launch_product.py','--status'],cwd=ROOT,env=env,capture_output=True,text=True,check=True).stdout
            stop=subprocess.run([str(python),'scripts/launch_product.py','--stop'],cwd=ROOT,env=env,capture_output=True,text=True,check=True).stdout
            output=process.communicate(timeout=10)[0]
            result={'environment':'LINUX_VERIFIED_EXISTING_DEPENDENCIES_PTH_HARNESS','fresh_dependency_install':'NOT_RUN','ready':True,'status_output':status,'stop_output':stop,'launcher_exit':process.returncode,'launcher_output':output,'runtime_manifest_removed':not(Path(directory)/'runtime.json').exists()}
            print(json.dumps(result,ensure_ascii=False,indent=2))
            assert process.returncode==0
            assert result['runtime_manifest_removed']
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)

if __name__=='__main__':main()
