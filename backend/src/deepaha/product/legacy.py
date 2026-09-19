"""Read-only bridge using SQL reflection; never import legacy workflow services."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import uuid
import zipfile
from sqlalchemy import MetaData,Table,select,func,inspect
from .errors import Problem

TABLES=['sources','opportunities','opportunity_versions','personal_users','reviewer_accounts','investigation_tasks','local_human_test_runs','raw_artifacts']

def inventory(engine):
    names=set(inspect(engine).get_table_names());out={}
    with engine.connect() as c:
        for name in TABLES:
            if name not in names:out[name]={'exists':False};continue
            t=Table(name,MetaData(),autoload_with=engine)
            out[name]={'exists':True,'count':c.scalar(select(func.count()).select_from(t))}
    return {'mode':'READ_ONLY','tables':out,'note':'旧审核记录不会自动升级为整体收录；旧账号不会自动授予新权限。'}

def list_runs(engine,offset=0,limit=30):
    if not inspect(engine).has_table('investigation_tasks'):return []
    t=Table('investigation_tasks',MetaData(),autoload_with=engine)
    columns=[t.c[x] for x in ['task_id','status','error_code','created_at','updated_at'] if x in t.c]
    with engine.connect() as c:
        return [{k:(v.isoformat() if hasattr(v,'isoformat') else str(v) if isinstance(v,uuid.UUID) else v) for k,v in r._mapping.items()} for r in c.execute(select(*columns).order_by(t.c.created_at.desc()).offset(offset).limit(min(limit,50)))]

def export_task(engine,objects,task_id,output):
    output=Path(output)
    if output.exists():raise Problem('目标文件已存在，不覆盖')
    try:ident=uuid.UUID(task_id)
    except ValueError:raise Problem('旧任务标识不正确')
    if not inspect(engine).has_table('investigation_tasks'):raise Problem('未找到旧调查任务表',404)
    md=MetaData();t=Table('investigation_tasks',md,autoload_with=engine)
    with engine.connect() as c:
        typed=ident if engine.dialect.name=='postgresql' else str(ident)
        task=c.execute(select(t).where(t.c.task_id==typed)).mappings().first()
        if not task:raise Problem('旧任务不存在',404)
        manifest=task.get('result_objects') or {}
        if isinstance(manifest,str):manifest=json.loads(manifest)
        if not manifest:raise Problem('此任务未保存可导出的返回文件',409)
        files={}
        for name,key in manifest.items():
            if not isinstance(name,str) or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name:raise Problem('旧返回目录包含异常路径',409)
            b=objects.get_bytes(key=key)
            if hashlib.sha256(b).hexdigest()!=key.rsplit('/',1)[-1]:raise Problem('旧返回文件校验失败',409)
            files[name]=b
        if inspect(engine).has_table('investigation_materials') and inspect(engine).has_table('raw_artifacts'):
            m=Table('investigation_materials',md,autoload_with=engine);a=Table('raw_artifacts',md,autoload_with=engine)
            for material,raw_key in c.execute(select(m.c.metadata_snapshot,a.c.object_key).join(a,m.c.raw_artifact_id==a.c.artifact_id).where(m.c.task_id==typed)):
                remote=material.get('remote_path','');name='artifacts/'+Path(remote).name
                if name in files:raise Problem('旧附件存在同名路径，请按原目录人工导出，未生成不完整包',409)
                b=objects.get_bytes(key=raw_key)
                if material.get('sha256') and hashlib.sha256(b).hexdigest()!=material['sha256']:raise Problem('旧原件校验失败',409)
                files[name]=b
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
        for name,b in files.items():z.writestr(name,b)
        z.writestr('legacy-origin.json',json.dumps({'task_id':task_id,'source_id':str(task['source_id']),'previous_status':task['status'],'old_decision_not_promoted':True},ensure_ascii=False,indent=2))
