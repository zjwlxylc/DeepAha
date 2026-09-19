#!/usr/bin/env python3
"""Cross-platform local launcher. Never stops an unrelated process or touches old DBs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
VENV=ROOT/'.venv-product'
DATA=Path(os.environ.get('DEEPAHA_DATA_DIR',str(Path.home()/'deepaha-data'))).resolve()
PYTHON=VENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
MANIFEST=DATA/'runtime.json'
STOP_REQUEST=DATA/'.stop-requested'


def check_owned(record,project):
    import psutil
    try:
        process=psutil.Process(record['pid'])
        if abs(process.create_time()-record['created'])>1:return None
        if Path(process.cwd()).resolve()!=project/'backend':return None
        command=process.cmdline()
        if 'deepaha.product.cli' not in command:return None
        return process
    except (psutil.Error,KeyError,OSError):return None


def control(stop=False):
    if not MANIFEST.exists():print('没有本启动器管理的运行进程。');return 0
    import psutil
    manifest=json.loads(MANIFEST.read_text())
    if manifest.get('project')!=str(ROOT):raise RuntimeError('运行清单属于其他目录；拒绝操作。')
    if stop:STOP_REQUEST.touch()
    for record in manifest['processes']:
        process=check_owned(record,ROOT)
        print(record['role']+(': 运行中' if process else ': 已停止'))
        if process and stop:
            try:process.terminate()
            except psutil.NoSuchProcess:continue
            try:process.wait(timeout=10)
            except psutil.TimeoutExpired:
                # Recheck identity before any forceful termination.
                process=check_owned(record,ROOT)
                if process:process.kill()
    if stop:MANIFEST.unlink(missing_ok=True)
    return 0


def ensure_environment(install):
    if sys.version_info<(3,13) or sys.version_info>=(3,15):raise RuntimeError('请使用 Python 3.13 或 3.14。')
    requirement=ROOT/'backend/requirements-product.txt'
    stamp=hashlib.sha256(requirement.read_bytes()).hexdigest()
    marker=VENV/'.requirements-hash'
    ready=PYTHON.exists() and marker.exists() and marker.read_text()==stamp
    if not ready:
        if not install:raise RuntimeError('依赖尚未准备好。先运行：python scripts/launch_product.py --install')
        if not PYTHON.exists():subprocess.run([sys.executable,'-m','venv',str(VENV)],check=True)
        subprocess.run([str(PYTHON),'-m','pip','install','-r',str(requirement)],check=True)
        marker.write_text(stamp)
    if Path(sys.prefix).resolve()!=VENV.resolve():
        return subprocess.run([str(PYTHON),str(Path(__file__).resolve()),*sys.argv[1:]],check=False).returncode
    return None


def main():
    parser=argparse.ArgumentParser(description='DeepAha 本地启动器')
    parser.add_argument('--install',action='store_true',help='准备专用Python环境及依赖')
    parser.add_argument('--stop',action='store_true')
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if (args.stop or args.status) and not PYTHON.exists():
        print('专用环境尚不存在，本启动器没有需要管理的进程。');return 0
    if args.stop or args.status:
        if Path(sys.prefix).resolve()!=VENV.resolve():
            return subprocess.run([str(PYTHON),str(Path(__file__).resolve()),*sys.argv[1:]],check=False).returncode
        return control(args.stop)
    result=ensure_environment(args.install)
    if result is not None:return result
    if args.stop or args.status:return control(args.stop)
    if os.environ.get('DEEPAHA_DATABASE_URL','').startswith('postgresql'):
        raise RuntimeError('此启动器仅管理本地SQLite。PostgreSQL请按部署手册使用服务启动命令。')
    if not 1024<=args.port<=65535:raise RuntimeError('端口应为1024至65535。')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',args.port))==0:raise RuntimeError(f'端口{args.port}已被占用；未停止任何既有服务。')
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    environment={**os.environ,'PYTHONPATH':str(ROOT/'backend/src'),'DEEPAHA_DATA_DIR':str(DATA)}
    command=[str(PYTHON),'-m','deepaha.product.cli']
    import sqlite3
    database=DATA/'deepaha.db'
    def has_account():
        if not database.exists():return False
        with sqlite3.connect(database) as connection:
            tables=[x[0] for x in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            if 'product_accounts' not in tables:return False
            return connection.execute('SELECT COUNT(*) FROM product_accounts').fetchone()[0]>0
    def run_setup():
        for attempt in range(3):
            print('\n需要设置一个账号才能登录。账号可用英文或数字；密码至少 12 个字符，输入时不显示，输完按回车。')
            if subprocess.run(command+['setup'],cwd=ROOT/'backend',env=environment).returncode==0:return
            print(f'设置未完成（第 {attempt+1} 次）。常见原因：两次密码不一致，或密码少于 12 个字符。')
        raise RuntimeError('连续三次未完成账号设置。服务未启动；重新双击本脚本即可继续设置，已建好的数据不会丢。')
    if not database.exists():
        print('首次启动：创建独立产品数据目录，并设置首个账号。')
        run_setup()
    else:
        with sqlite3.connect(database) as connection:
            tables=[x[0] for x in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if 'product_meta' not in tables:raise RuntimeError('此目录不是新产品数据；先备份并按迁移手册检查，启动器不会改写。')
        if 'product_scout_batches' not in tables or 'product_task_source_contexts' not in tables:
            print('正在备份现有数据并补齐来源资产表；不覆盖已有账号、来源和总览。')
            subprocess.run(command+['upgrade'],cwd=ROOT/'backend',env=environment,check=True)
        # SG1 is an additive, backup-first projection upgrade.  The command is
        # idempotent: current databases are only checked, while an rc2 database
        # is backed up before actionable position/track targets are backfilled.
        print('正在检查具体岗位 / 赛道总览数据结构。')
        subprocess.run(command+['upgrade-sg1'],cwd=ROOT/'backend',env=environment,check=True)
        print('正在检查报名 / 申请时间语义；只使用已保存原件，不重新调用 WMA。')
        subprocess.run(command+['upgrade-sg5-1'],cwd=ROOT/'backend',env=environment,check=True)
        print('正在检查行动时间线、反馈候选与通知闭环。')
        subprocess.run(command+['upgrade-sg6'],cwd=ROOT/'backend',env=environment,check=True)
        print('正在检查资格证据编译投影；只编译已收录字段并复用原件证据，不增加逐字段人工审核。')
        subprocess.run(command+['upgrade-sg6-2'],cwd=ROOT/'backend',env=environment,check=True)
        print('正在检查 SG7 机会实验室；只增加隔离实验数据结构，不改正式事实、审核结果或 WMA 原件。')
        subprocess.run(command+['upgrade-sg7'],cwd=ROOT/'backend',env=environment,check=True)
        if not has_account():
            print('数据目录里还没有任何账号，补设首个账号后再启动服务。')
            run_setup()
    STOP_REQUEST.unlink(missing_ok=True)
    logs=DATA/'logs';logs.mkdir(exist_ok=True)
    processes=[];handles=[]
    import psutil
    try:
        for role,arguments in [('api',['serve','--port',str(args.port)]),('worker',['worker'])]:
            output=(logs/(role+'.log')).open('a',encoding='utf-8');handles.append(output)
            process=subprocess.Popen(command+arguments,cwd=ROOT/'backend',env=environment,stdout=output,stderr=subprocess.STDOUT)
            processes.append({'role':role,'pid':process.pid,'created':psutil.Process(process.pid).create_time()})
        MANIFEST.write_text(json.dumps({'project':str(ROOT),'processes':processes},indent=2))
        url=f'http://127.0.0.1:{args.port}'
        for _ in range(50):
            try:
                with urllib.request.urlopen(url+'/health/ready',timeout=1) as response:
                    if response.status==200:break
            except OSError:time.sleep(.2)
        else:raise RuntimeError('服务未就绪，请查看数据目录logs/api.log。')
        print('机会星图：'+url+'\n审核工作台：'+url+'/review/overview\n数据目录：'+str(DATA)+'\n关闭窗口或按Ctrl+C停止本次服务。')
        if not args.no_browser:webbrowser.open(url)
        while True:
            time.sleep(2)
            if STOP_REQUEST.exists():return 0
            if not check_owned(processes[0],ROOT):raise RuntimeError('API服务已退出，请查看日志。')
    except KeyboardInterrupt:return 0
    finally:
        for record in processes:
            process=check_owned(record,ROOT)
            if process:
                try:process.terminate()
                except psutil.NoSuchProcess:continue
                try:process.wait(timeout=10)
                except psutil.TimeoutExpired:pass
        MANIFEST.unlink(missing_ok=True)
        for handle in handles:handle.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,subprocess.CalledProcessError,OSError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
