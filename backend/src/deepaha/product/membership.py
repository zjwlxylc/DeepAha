"""R3 host integration. Shared auth, messages, privacy and pre-prompt authority."""
from datetime import timedelta
import json
from urllib.parse import quote
from sqlalchemy import select, update, delete, func
from deepaha_membership.db import (Store, orders, grants, submissions, watches, jobs,
    notices, idems, mutex, meta, row, rows)
from deepaha_membership.commerce import Commerce
from deepaha_membership.auth import Actor
from deepaha_membership.periods import stamp
from .models import Account, Profile, Meta, Task, now
from .errors import Problem


def initialize(product):
    store=Store(product.db.engine)
    store.initialize()
    Commerce(store).seed()


def notice_rows(c, owner):
    found=rows(c,select(notices).where(notices.c.owner==owner))
    def target(n):
        t=n['target'] or ''
        if t.startswith('opportunity:'):
            return '/app/opportunity/'+quote(t.split(':',1)[1],safe='')
        return {'feedback':'/app/sources','account':'/app/subscription','orders':'/app/subscription',
                'watches':'/app/tracking'}.get(t,'/app/tracking')
    return [dict(id='mbr:'+n['id'],title=n['title'],body=n['body'],kind='SERVICE',
                 state='READ' if n['read_at'] else 'UNREAD',opportunity_id=None,
                 target_url=target(n),created_at=n['created_at']) for n in found]


def mark_notice(c, owner, id):
    raw=id.removeprefix('mbr:')
    n=row(c,select(notices).where(notices.c.id==raw,notices.c.owner==owner))
    if not n:raise Problem('通知不存在',404)
    c.execute(update(notices).where(notices.c.id==raw,notices.c.owner==owner).values(read_at=stamp(now())))


def unread_count(c, owner):
    return c.execute(select(func.count()).select_from(notices).where(notices.c.owner==owner,notices.c.read_at.is_(None))).scalar() or 0


def export(c, owner):
    # Never join other users' submissions through the shared lead relation.
    result={}
    for name,table in [('orders',orders),('grants',grants),('submissions',submissions),
                       ('watches',watches),('jobs',jobs),('notices',notices)]:
        result[name]=rows(c,select(table).where(table.c.owner==owner))
    result['retention_notice']='清理个人记录会删除跟踪、网站提交私文和服务通知；必要的订单条款、权益和核对记录保留，不会自动退款。'
    return result


def erase(session, owner):
    """Same transaction as core privacy erase; no stale replay of removed text."""
    c=session.connection()
    c.execute(update(mutex).where(mutex.c.id==1).values(sequence=mutex.c.sequence+1))
    owned=rows(c,select(jobs).where(jobs.c.owner==owner))
    for job in owned:
        # Stable request_key also fences jobs whose original dispatch response was lost.
        task=session.scalar(select(Task).where(Task.request_key=='mbr:'+job['id']))
        if task and task.status not in ('READY','FAILED','CANCELLED'):
            task.status='CANCELLED';task.updated_at=now()
    c.execute(delete(jobs).where(jobs.c.owner==owner))
    c.execute(delete(watches).where(watches.c.owner==owner))
    c.execute(delete(submissions).where(submissions.c.owner==owner))
    c.execute(delete(notices).where(notices.c.owner==owner))
    c.execute(update(orders).where(orders.c.owner==owner).values(note=''))
    # Private submission/order text can also be present in cached idempotent responses.
    # Keep commercial keys with scrubbed snapshots: never resurrect a paid order.
    for x in rows(c,select(idems).where(idems.c.actor==owner)):
        if x['action'] in ('create_order','accept_quote','cancel'):
            result=x['result']
            if isinstance(result,dict):result={**result,'note':''}
            c.execute(update(idems).where(idems.c.actor==owner,idems.c.action==x['action'],idems.c.key==x['key']).values(result=result))
        else:
            c.execute(delete(idems).where(idems.c.actor==owner,idems.c.action==x['action'],idems.c.key==x['key']))
    # Reviewer/operator idempotency caches may contain this user's submission via
    # supplement responses only (owned actor); public lead records contain no private notes.


def assert_task_authorized(product, session, task):
    """Run before remote session creation and immediately before prompt dispatch."""
    if not task.request_key.startswith('mbr:'):return
    from deepaha_membership.db import leads
    c=session.connection()
    job=row(c,select(jobs).where(jobs.c.id==task.request_key[4:]))
    if not job:raise Problem('定制服务授权已清理，停止新的远程调查',409,'MEMBERSHIP_AUTHORITY_REVOKED')
    watch=row(c,select(watches).where(watches.c.id==job['watch_id']))
    account=session.scalar(select(Account).where(Account.username==job['owner'],Account.active.is_(True)))
    from deepaha_membership.tracking import Tracking
    tracking=Tracking(Store(product.db.engine),Commerce(Store(product.db.engine)),None)
    if not account or not watch or watch['id'] not in tracking._effective_ids(c,job['owner'],'SITE'):
        raise Problem('订阅已到期、账号已停用或跟踪已暂停，未发送调查',409,'MEMBERSHIP_AUTHORITY_REVOKED')
    lead=row(c,select(leads).where(leads.c.id==watch['config']['lead_id']))
    if not lead or lead['state']!='APPROVED' or not lead['collection_enabled'] or lead['source_id']!=task.source_id:
        raise Problem('定制来源授权已变化，未发送调查',409,'MEMBERSHIP_SOURCE_REVOKED')


DEFAULT_RUNTIME={'version':0,'enabled':False,'allow_site_enqueue':False,'max_jobs':3,
                 'connection':'default','actor':None,'next_due':None,'last_run':None,'last_result':None}
RUNTIME_KEY='services_runtime_v1'


def runtime_config(product):
    with product.db.tx(False) as s:
        value=s.get(Meta,RUNTIME_KEY)
        return {**DEFAULT_RUNTIME,**(json.loads(value.value) if value else {})}


def save_runtime(product, actor, data):
    from .config import BindingRegistry
    if type(data.get('enabled')) is not bool or type(data.get('allow_site_enqueue')) is not bool:
        raise Problem('开关值不正确')
    if type(data.get('max_jobs')) is not int or not 1<=data['max_jobs']<=20:raise Problem('单轮任务上限应为1至20')
    with product.db.tx() as s:
        product._account(s,actor,'operator')
        old=s.get(Meta,RUNTIME_KEY)
        config={**DEFAULT_RUNTIME,**(json.loads(old.value) if old else {})}
        if data['version']!=config['version']:raise Problem('运行设置已变化，请刷新',409,'STALE_VERSION')
        config.update({k:data[k] for k in ('enabled','allow_site_enqueue','max_jobs','connection')})
        config.update(version=config['version']+1,actor=actor,next_due=None)
        value=json.dumps(config,ensure_ascii=False)
        if old:old.value=value
        else:s.add(Meta(key=RUNTIME_KEY,value=value))
        product._audit(s,actor,'CONFIGURE_SERVICES_RUNTIME','services',
                       '允许指定网站调查' if config['allow_site_enqueue'] else '仅检查已发布目录')
        return config


def scheduled_tick(product, settings, *, force=False):
    """Existing worker calls this. Shared short lease fences duplicate processes."""
    from deepaha_membership.cli import tick
    with product.db.tx() as s:
        record=s.get(Meta,RUNTIME_KEY)
        if not record:return {'state':'DISABLED'}
        config={**DEFAULT_RUNTIME,**json.loads(record.value)}
        if not config['enabled']:return {'state':'DISABLED'}
        at=stamp(now())
        if config.get('lease_until') and config['lease_until']>at:return {'state':'BUSY'}
        if not force and config['next_due'] and config['next_due']>at:return {'state':'NOT_DUE'}
        product._account(s,config['actor'],'operator')
        config['lease_until']=stamp(now()+timedelta(minutes=15));config['next_due']=stamp(now()+timedelta(hours=1))
        record.value=json.dumps(config)
    try:
        result=tick(product,settings,config['actor'],allow_site_enqueue=config['allow_site_enqueue'],
                    max_jobs=config['max_jobs'],connection=config['connection'])
        result={'state':'COMPLETED','topics':result['topics'],'site_publications':result['site_publications'],
                'refreshed':len(result['refreshed']),'dispatched':len(result['dispatched']),
                'skipped':len(result['skipped'])}
    except Exception as exc:
        result={'state':'FAILED','code':getattr(exc,'code','SERVICES_TICK_FAILED')}
    with product.db.tx() as s:
        record=s.get(Meta,RUNTIME_KEY)
        current=json.loads(record.value)
        current.update(lease_until=None,last_run=stamp(now()),last_result=result)
        record.value=json.dumps(current)
    return result


def mount_host(app, product, settings, user):
    from fastapi import Request
    from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
    from deepaha_membership.api import mount
    tracking=mount(app,product,settings)
    class RuntimeIn(BaseModel):
        model_config=ConfigDict(extra='forbid')
        version:StrictInt=Field(ge=0)
        enabled:StrictBool
        allow_site_enqueue:StrictBool
        max_jobs:StrictInt=Field(ge=1,le=20)
        connection:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    @app.get('/api/membership/runtime-status')
    def runtime_status():
        r=runtime_config(product)
        return {k:r[k] for k in ('enabled','allow_site_enqueue','last_run')}
    @app.get('/api/membership/manage/runtime')
    def get_runtime(req:Request):
        user(req,'operator')
        return runtime_config(product)
    @app.put('/api/membership/manage/runtime')
    def put_runtime(data:RuntimeIn,req:Request):
        actor=user(req,'operator',True)
        from .config import BindingRegistry
        if data.connection not in BindingRegistry(settings.data_dir,settings.mode).definitions():
            raise Problem('宿主未登记该执行连接',404,'UNKNOWN_CONNECTION')
        return save_runtime(product,actor,data.model_dump())
    @app.post('/api/membership/manage/runtime/check')
    def check_runtime(req:Request):
        # This is a write + explicit operator action, not a GET side effect.
        user(req,'operator',True)
        return scheduled_tick(product,settings,force=True)
    return tracking
