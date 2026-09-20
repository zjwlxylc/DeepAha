"""Opt-in host-only WMA capacity probe. There is deliberately no grant-upload API.

Only real SDK responses can complete this path; no fixture/simulator flag exists.
The probe creates isolated remote sessions and local evidence, never publications.
LIVE denotes real transport/contract observations, NOT semantic accuracy or a vendor SLA.
"""
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
from sqlalchemy import select
from .adapter import safe_url,project,parse_json
from .models import DispatchValidation,TaskDispatch,Task,Meta,now
from .auth import aware
from .dispatch_policy import serial_model
from .errors import Problem
from .storage import MAX_FILE,MAX_TOTAL,MAX_FILES


def request_peak(records):
    events=[]
    for r in records:
        if r.get('prompt_started') is not None and r.get('prompt_finished') is not None:
            events.extend([(r['prompt_started'],1),(r['prompt_finished'],-1)])
    active=peak=0
    for _,delta in sorted(events):active+=delta;peak=max(peak,active)
    return peak


def _code(error):
    value=getattr(error,'code','PROBE_FAILED')
    return value if isinstance(value,str) and re.fullmatch(r'[A-Z0-9_]{1,100}',value) else 'PROBE_FAILED'


def _write(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)


async def _execute_live(product,registry,*,actor,connection_ref,source_id,url,parallel,max_prompts,budget_seconds,confirmed,evidence_dir):
    if confirmed is not True or parallel not in (1,2,4) or max_prompts!=parallel or not 60<=budget_seconds<=1800:
        raise Problem('须明确授权远程调用，并使max-prompts等于1/2/4并发数；单任务预算60至1800秒',409,'LIVE_AUTHORIZATION_REQUIRED')
    url=safe_url(url)
    with product.db.tx(False) as s:
        product._account(s,actor,'operator');source=product._source(s,source_id)
        if not url or not source['enabled'] or not source['active'] or urlsplit(url).hostname not in source['allowed_hosts']:
            raise Problem('仅能使用已批准且启用的来源和允许网址',409,'SOURCE_POLICY_CHANGED')
    factory=registry.factory(connection_ref)
    if not factory:raise Problem('宿主连接未配置或未启用',409,'NOT_CONFIGURED')
    probe=factory()
    try:release=await probe.inspect_release()
    finally:await probe.aclose()
    fingerprint=registry.fingerprint(connection_ref,release)
    if parallel>1 and serial_model(release.get('published_model')):raise Problem('未知模型或AGENS按项目策略串行',409,'SERIAL_REQUIRED')
    with product.db.tx(False) as s:
        previous=s.scalar(select(DispatchValidation).where(DispatchValidation.connection_ref==connection_ref,
            DispatchValidation.binding_fingerprint==fingerprint,DispatchValidation.origin=='LIVE',DispatchValidation.passed.is_(True),
            DispatchValidation.parallel==(1 if parallel==2 else 2))) if parallel>1 else True
        if not previous:raise Problem('必须按1→2→4逐级验证同一个发布绑定',409,'PREVIOUS_PROBE_REQUIRED')
    root=Path(evidence_dir).resolve()
    if root.exists():raise Problem('实测证据目录必须尚不存在，避免覆盖历史',409,'EVIDENCE_EXISTS')
    root.mkdir(parents=True,mode=0o700)
    report={'schema':'deepaha.live-capacity/1','origin':'LIVE','status':'RUNNING','started_at':now().isoformat(),
        'connection_ref':connection_ref,'binding_fingerprint':fingerprint,'model':release.get('published_model'),
        'parallel':parallel,'max_prompts':max_prompts,'budget_seconds':budget_seconds,'records':[],
        'grant_receipt_file':'grant-receipt.json (only if grant is committed)','production_publication_modified':False,'semantic_accuracy_measured':False,
        'observation':'Overlapping client requests and returned result contracts; not proof of vendor internal parallel execution.'}
    def persist():_write(root/'report.json',report)
    persist()
    async def one(index):
        record={'index':index,'state':'CREATING','prompt_started':None,'prompt_finished':None,'remote_state':'NOT_SENT'}
        report['records'].append(record);persist();client=None;key='probe_'+uuid.uuid4().hex
        folder=root/key;folder.mkdir(mode=0o700);workspace='/workspace/deepaha-validation/'+key
        try:
            client=factory()
            actual=await client.inspect_release()
            if registry.fingerprint(connection_ref,actual)!=fingerprint:raise Problem('执行绑定变化',409,'BINDING_CHANGED')
            def checkpoint(runtime_id,session_id):
                record.update(runtime_id=runtime_id,session_id=session_id);persist()
            await client.create(key,checkpoint=checkpoint)
            schema_dir=Path(__file__).parents[1]/'investigations'/'schemas'
            for name in ('opportunities.schema.json','evidence.schema.json'):await client.upload(workspace+'/'+name,(schema_dir/name).read_bytes())
            task={'task_id':key,'seed_url':url,'allowed_hosts':source['allowed_hosts'],'source_brief':source['brief'],
                'scope':'仅调查指定单份公告及相关附件；栏目仅第一可访问页，逐条注明未完成项。','budget_seconds':budget_seconds,
                'schema_directory':workspace,'output_directory':workspace+'/result','validation_only':True}
            await client.upload(workspace+'/task.json',json.dumps(task,ensure_ascii=False).encode())
            with product.db.tx(False) as s:
                product._account(s,actor,'operator');fresh=product._source(s,source_id)
                if not fresh['enabled'] or fresh['policy_version']!=source['policy_version']:raise Problem('来源政策变化',409,'SOURCE_POLICY_CHANGED')
            record.update(state='PROMPT_STARTED',prompt_started=time.monotonic(),remote_state='UNKNOWN');persist()
            stop=await client.prompt(f'读取 {workspace}/task.json 和同目录两份输出schema。执行已发布的官方机会调查职责，仅按任务范围调查公开官方来源。不使用个人数据、不写DeepAha数据库、不批准发布。将 report.md、opportunities.json、evidence.json 写入 {workspace}/result；原件放result/artifacts并在evidence中给相对路径。完整性优于篇幅，未取得的材料如实记录，不绕过登录或访问挑战。',timeout_seconds=budget_seconds)
            record.update(prompt_finished=time.monotonic(),stop_reason=stop,remote_state='ENDED',state='COLLECTING');persist()
            if stop!='end_turn':raise Problem('调查未正常结束，不授予并发能力',409,'PROBE_INCOMPLETE')
            files={}
            for name in ('report.md','opportunities.json','evidence.json'):files[name]=await client.download(workspace+'/result/'+name,max_bytes=MAX_FILE)
            evidence=parse_json(files['evidence.json'])
            for a in evidence.get('artifacts',[])[:MAX_FILES-3]:
                if not isinstance(a,dict):raise Problem('材料目录格式错误',409,'PROBE_CONTRACT_INVALID')
                name=a.get('local_path') or a.get('path') or a.get('filename')
                if not isinstance(name,str):continue
                if name.startswith(workspace+'/result/'):name=name[len(workspace+'/result/'):]
                path=PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or str(path)!=name or name in files:
                    raise Problem('原件路径不安全或重复',409,'PROBE_CONTRACT_INVALID')
                files[name]=await client.download(workspace+'/result/'+name,max_bytes=MAX_FILE)
                if sum(map(len,files.values()))>MAX_TOTAL:raise Problem('回收文件超过上限',413,'RESULT_SIZE_LIMIT')
            projected=project(files,source,url)
            if not projected.get('can_approve') or projected.get('blockers'):raise Problem('返回未通过机械契约检查',409,'PROBE_CONTRACT_INVALID')
            hashes={}
            for name,content in files.items():
                target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
                hashes[name]={'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
            record.update(state='COMPLETE',files=hashes,mechanical_contract_ok=True);persist()
        except Exception as error:
            record.update(state='FAILED',error_code=_code(error));persist()
        finally:
            if client:
                try:await client.aclose()
                except Exception:
                    record.update(state='FAILED',cleanup_code='CLIENT_CLOSE_FAILED');persist()
    # A transport exception is recorded per probe, never hidden by another success.
    await asyncio.gather(*(one(i) for i in range(parallel)))
    probe=None;same=False
    try:
        probe=factory();final_release=await probe.inspect_release();same=registry.fingerprint(connection_ref,final_release)==fingerprint
    except Exception:same=False
    finally:
        if probe:
            try:await probe.aclose()
            except Exception:same=False
    peak=request_peak(report['records']);passed=same and all(r['state']=='COMPLETE' for r in report['records']) and peak==parallel
    report.update(status='PASS' if passed else 'FAIL',finished_at=now().isoformat(),observed_request_peak=peak,binding_unchanged=same)
    persist()
    if passed:
        # Only this executing, authenticated host path can produce a LIVE record.
        product.observe_binding(connection_ref,fingerprint,release,actor=actor)
        digest=hashlib.sha256((root/'report.json').read_bytes()).hexdigest()
        with product.db.tx() as s:
            product._account(s,actor,'operator')
            s.add(DispatchValidation(connection_ref=connection_ref,binding_fingerprint=fingerprint,parallel=parallel,
                origin='LIVE',passed=True,report_sha256=digest))
            product._audit(s,actor,'LIVE_DISPATCH_VALIDATION',connection_ref,f'实测并发{parallel}；报告SHA256={digest}')
        # Keep report immutable: grant receipt is separate and refers to exact report bytes.
        _write(root/'grant-receipt.json',{'grant_created':True,'report_sha256':digest,'parallel':parallel,'binding_fingerprint':fingerprint})
    return {'status':report['status'],'grant_created':passed,'parallel':parallel,'evidence_dir':str(root),'production_publication_modified':False}


async def validate_live(product,registry,*,actor,connection_ref,source_id,url,parallel,max_prompts,budget_seconds,confirmed,evidence_dir):
    """Reserve the database's dispatch lane before any paid probe can start.

    The guard is intentionally durable and not time-expired: a killed probe may
    still be running remotely. Terminal reports release it; unknown acceptance
    needs explicit host confirmation. Other databases/third-party callers cannot
    be coordinated here and must be stopped by the host operator.
    """
    if confirmed is not True or parallel not in (1,2,4) or max_prompts!=parallel or not 60<=budget_seconds<=1800:
        raise Problem('须明确授权远程调用和预算',409,'LIVE_AUTHORIZATION_REQUIRED')
    root=Path(evidence_dir).resolve()
    if root.exists():raise Problem('实测证据目录必须尚不存在',409,'EVIDENCE_EXISTS')
    run_id=uuid.uuid4().hex
    with product.db.tx() as s:
        product._account(s,actor,'operator')
        occupied=s.scalar(select(Task.id).where(Task.status=='RUNNING'))
        reserved=any(d.remote_pending or (d.lease_owner and d.lease_expires_at and aware(d.lease_expires_at)>now()) for d in s.scalars(select(TaskDispatch)))
        if s.get(Meta,'wma_live_probe') or occupied or reserved:
            raise Problem('已有实测或远端/本地任务占用；请先确认其已结束',409,'LIVE_PROBE_BUSY')
        s.add(Meta(key='wma_live_probe',value=json.dumps({'run_id':run_id,'connection_ref':connection_ref,'status':'RUNNING','started_at':now().isoformat()})))
        product._audit(s,actor,'LIVE_PROBE_RESERVED',run_id,'临时停止新调度；单任务预算='+str(budget_seconds))
    try:
        return await _execute_live(product,registry,actor=actor,connection_ref=connection_ref,source_id=source_id,url=url,
            parallel=parallel,max_prompts=max_prompts,budget_seconds=budget_seconds,confirmed=confirmed,evidence_dir=root)
    finally:
        unknown=False
        report_path=root/'report.json'
        if report_path.exists():
            try:unknown=any(r.get('remote_state')=='UNKNOWN' for r in json.loads(report_path.read_text(encoding='utf-8')).get('records',[]))
            except (ValueError,OSError):unknown=True
        with product.db.tx() as s:
            guard=s.get(Meta,'wma_live_probe')
            if guard and json.loads(guard.value).get('run_id')==run_id:
                if unknown:
                    data=json.loads(guard.value);data['status']='NEEDS_CONFIRMATION';guard.value=json.dumps(data)
                else:s.delete(guard)
                product._audit(s,actor,'LIVE_PROBE_RELEASE_STATE',run_id,'远端状态不明，保留占用' if unknown else '本轮无未结束请求；解除占用')


def resolve_probe(product,*,actor,confirmed,reason):
    """Host-only assertion, not remote cancellation and not a validation grant."""
    if confirmed is not True or not isinstance(reason,str) or not reason.strip() or len(reason)>500:
        raise Problem('请确认实测进程与所有远端会话均已结束并填写依据',409,'REMOTE_CONFIRMATION_REQUIRED')
    with product.db.tx() as s:
        product._account(s,actor,'operator');guard=s.get(Meta,'wma_live_probe')
        if not guard:return {'released':False,'remote_stop_called':False}
        run_id=json.loads(guard.value).get('run_id','unknown')
        s.delete(guard);product._audit(s,actor,'LIVE_PROBE_MANUAL_RELEASE',run_id,reason.strip())
    return {'released':True,'remote_stop_called':False}
