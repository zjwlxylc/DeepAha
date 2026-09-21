#!/usr/bin/env python3
"""Produce an UNVERIFIED integration candidate from the exact user-supplied R2 ZIP.
Never overwrite a checkout, modify a running database, push, merge, or deploy.
"""
from pathlib import Path,PurePosixPath
import argparse,ast,hashlib,json,re,shutil,stat,tempfile,zipfile
EXPECTED_SHA='929ab1518f53717018864ffc7904600d9d8a4ca3f1bba52a776631e3dbb3f467'
HOOK='    from deepaha_membership.api import mount as mount_membership\n    mount_membership(app,p,settings)\n'
ANCHOR='    mount_access(app,p,user)\n'
MAX_FILES=20000
MAX_BYTES=2_000_000_000
RESERVED={'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def safe_extract(archive,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();seen=set();total=0
        if len(infos)>MAX_FILES:raise ValueError('压缩包条目数超限')
        for i in infos:
            n=i.orig_filename;p=PurePosixPath(n)
            if not n or n.startswith('/') or '\\' in n or ':' in n or any(x in ('.','..') for x in n.split('/')):
                raise ValueError('压缩包包含不安全路径')
            if any(x.endswith((' ','.')) or x.split('.')[0].upper() in RESERVED for x in p.parts):raise ValueError('压缩包路径不适用于Windows')
            folded=str(p).casefold()
            if folded in seen:raise ValueError('压缩包有重名或大小写冲突路径')
            seen.add(folded)
            if stat.S_ISLNK(i.external_attr>>16) or i.flag_bits&1:raise ValueError('不接收符号链接或加密压缩包')
            total+=i.file_size
            if total>MAX_BYTES or i.file_size>256_000_000:raise ValueError('解压容量超限')
        # Validate all paths before writing any member.
        for i in infos:
            target=destination.joinpath(*PurePosixPath(i.filename).parts)
            if i.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():raise ValueError('拒绝覆盖解压目标')
            with z.open(i) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)


def patch_api(source):
    if source.count(ANCHOR)!=1 or 'deepaha_membership' in source:raise ValueError('R2接入锚点不唯一、已接入或与已知结构不同；停止自动组装')
    tree=ast.parse(source)
    if not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='create_app' for n in tree.body):raise ValueError('create_app结构不兼容')
    patched=source.replace(ANCHOR,ANCHOR+HOOK)
    ast.parse(patched)
    return patched


def assemble(archive,output,addon):
    archive,output,addon=map(Path,(archive,output,addon))
    if sha(archive)!=EXPECTED_SHA:raise ValueError('原始R2压缩包SHA-256不匹配，拒绝用其他版本替代')
    if output.exists():raise FileExistsError('输出已存在，拒绝覆盖')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='r2-membership-') as work:
        work=Path(work);safe_extract(archive,work)
        matches=list(work.glob('**/backend/src/deepaha/product/api.py'))
        if len(matches)!=1:raise ValueError('无法唯一定位R2产品API')
        api=matches[0];root=api.parents[4]
        if not (root/'CHANGESET_MOBILE_R2.json').exists():raise ValueError('缺少R2变更清单，停止组装')
        originals={str(p.relative_to(work)):sha(p) for p in work.rglob('*') if p.is_file()}
        raw=api.read_bytes();source=raw.decode('utf-8-sig');newline='\r\n' if b'\r\n' in raw else '\n'
        patched=patch_api(source.replace('\r\n','\n'))
        api.write_bytes(patched.replace('\n',newline).encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'))
        target=root/'backend/src/deepaha_membership'
        if target.exists() or (root/'membership-addon').exists():raise ValueError('目标已包含订阅模块，停止覆盖')
        ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','*.pyc','*.db','.demo','.venv','.git')
        shutil.copytree(addon/'src/deepaha_membership',target,ignore=ignore)
        installation=root/'membership-addon';installation.mkdir()
        shutil.copy2(addon/'pyproject.toml',installation/'pyproject.toml')
        shutil.copytree(addon/'src',installation/'src',ignore=ignore)
        for name in ('docs','tests'):
            if (addon/name).exists():shutil.copytree(addon/name,installation/name,ignore=ignore)
        changed=[{'path':n,'before_sha256':h,'after_sha256':sha(work/n)} for n,h in originals.items() if sha(work/n)!=h]
        if len(changed)!=1 or changed[0]['path']!=str(api.relative_to(work)):raise ValueError('检测到额外原文件变动，停止交付')
        receipt=dict(status='UNVERIFIED_INTEGRATION_CANDIDATE',baseline_sha256=EXPECTED_SHA,modified_baseline_files=changed,original_files=len(originals),
            full_r2_tests_run=False,real_provider_test_run=False,deployed=False,
            next_steps=['在候选副本安装membership-addon依赖','停止服务并备份完整数据，显式初始化mbr表','接入R2导航及统一消息/个人数据生命周期','重跑R2和新增测试，核对真实来源/权限/支付边界','经人工验收后再考虑合并或部署'])
        (root/'MEMBERSHIP_ASSEMBLY.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        (root/'MEMBERSHIP_READ_FIRST.md').write_text('# 未验收整合候选包\n\n只修改原api.py接入点，其余原文件保留。原R2指纹清单因此不再代表新整包。请先读membership-addon/docs/03_RUN_AND_INTEGRATE.md。\n\n不能直接替换线上程序；未完成R2全套回归、旧导航/消息中心/个人数据清理/来源默认启用策略、PostgreSQL及真实WMA验证。\n',encoding='utf-8')
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(work.rglob('*')):
                if p.is_file():z.write(p,str(p.relative_to(work)))
        with zipfile.ZipFile(output) as z:
            if z.testzip() is not None:raise ValueError('输出ZIP校验失败')
        receipt['output_sha256']=sha(output)
        output.with_suffix('.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',required=True);p.add_argument('--output',required=True)
    args=p.parse_args()
    print(json.dumps(assemble(args.baseline,args.output,Path(__file__).resolve().parents[1]),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
