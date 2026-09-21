"""Membership-authorized watches. No background thread or implicit provider call."""
from datetime import timedelta
import re
from sqlalchemy import select, insert, update, func
from .db import watches, jobs, leads, submissions, notices, row, rows, uid
from .periods import parse, stamp
from .commerce import bounded_text
from .errors import require, DomainError
from .urls import validate_public_dns

ACTIVE_JOBS=('QUEUED','DISPATCHING','RETRYABLE','CORE_QUEUED','CORE_RUNNING')

class Tracking:
    def __init__(self,store,commerce,core,dns=validate_public_dns):
        self.s,self.commerce,self.core,self.dns=store,commerce,core,dns

    def _effective_ids(self,c,owner,kind):
        if self.core and hasattr(self.core,'owner_active') and not self.core.owner_active(c,owner):return set()
        e=self.commerce._entitlements(c,owner)
        limit=e['topic_limit' if kind=='TOPIC' else 'site_limit']
        cap='topic_watch' if kind=='TOPIC' else 'site_watch'
        if cap not in e['capabilities']:return set()
        return set(c.execute(select(watches.c.id).where(watches.c.owner==owner,watches.c.kind==kind,watches.c.enabled.is_(True)).order_by(watches.c.created_at,watches.c.id).limit(limit)).scalars())

    def _quota(self,c,a,kind):
        e=self.commerce._entitlements(c,a.name)
        cap='topic_watch' if kind=='TOPIC' else 'site_watch'
        require(cap in e['capabilities'],'当前服务不包含此跟踪能力',403,'ENTITLEMENT_REQUIRED')
        limit=e['topic_limit' if kind=='TOPIC' else 'site_limit']
        count=c.execute(select(func.count()).select_from(watches).where(watches.c.owner==a.name,watches.c.kind==kind,watches.c.enabled.is_(True))).scalar()
        require(count<limit,'已达到当前服务的跟踪数量，请暂停不再需要的项目',409,'QUOTA_EXCEEDED')

    def _create(self,c,a,kind,config):
        self._quota(c,a,kind)
        w=dict(id=uid(),owner=a.name,kind=kind,config=config,enabled=True,version=1,created_at=self.s.time(),last_checked=None,last_error=None)
        c.execute(insert(watches).values(**w));self.s.audit(c,a.name,'CREATE_WATCH',w['id'],{'kind':kind})
        return w

    def create_topic(self,a,name,q,kind,region,key):
        data=dict(name=bounded_text(name,100,'主题名称'),q=bounded_text(q,200,'关键词',0),kind=bounded_text(kind,100,'机会类别',0),region=bounded_text(region,100,'地区',0))
        require(data['q'] or data['kind'] or data['region'],'至少填写关键词、类别或地区之一')
        with self.s.write() as c:return self.s.idempotent(c,a.name,'create_topic',key,data,lambda:self._create(c,a,'TOPIC',data))

    def create_site(self,a,submission_id,key):
        with self.s.write() as c:
            def action():
                sub=row(c,select(submissions).where(submissions.c.id==submission_id,submissions.c.owner==a.name));require(sub,'网站提交记录不存在',404)
                lead=row(c,select(leads).where(leads.c.id==sub['lead_id']));require(lead['state']=='APPROVED','网站须先通过线索审核',409,'REVIEW_REQUIRED')
                existing=rows(c,select(watches).where(watches.c.owner==a.name,watches.c.kind=='SITE'))
                old=next((w for w in existing if w['config']['lead_id']==lead['id']),None)
                if old:return old
                return self._create(c,a,'SITE',dict(name=lead['name'],lead_id=lead['id'],url=lead['approved_url']))
            return self.s.idempotent(c,a.name,'create_site_watch',key,{'submission_id':submission_id},action)

    def mine(self,a,manage=False):
        if manage:a.need('operator')
        with self.s.read() as c:
            q=select(watches).order_by(watches.c.created_at.desc(),watches.c.id).limit(500)
            if not manage:q=q.where(watches.c.owner==a.name)
            out=rows(c,q);cache={}
            for w in out:
                key=(w['owner'],w['kind'])
                if key not in cache:cache[key]=self._effective_ids(c,*key)
                w['effective']=w['id'] in cache[key]
            return out

    def toggle(self,a,id,version,enabled,key):
        require(type(enabled) is bool,'启用状态不正确')
        with self.s.write() as c:
            def action():
                w=row(c,select(watches).where(watches.c.id==id));require(w and (w['owner']==a.name or a.has('operator')),'跟踪不存在',404)
                require(w['version']==version,'跟踪设置已变化',409,'STALE_VERSION')
                if enabled and not w['enabled']:
                    from .auth import Actor
                    self._quota(c,Actor(w['owner']),'TOPIC' if w['kind']=='TOPIC' else 'SITE')
                c.execute(update(watches).where(watches.c.id==id).values(enabled=enabled,version=version+1))
                self.s.audit(c,a.name,'WATCH_ENABLE' if enabled else 'WATCH_PAUSE',id)
                return row(c,select(watches).where(watches.c.id==id))
            return self.s.idempotent(c,a.name,'toggle_watch',key,dict(id=id,version=version,enabled=enabled),action)

    def _due(self,c,w):
        if w['id'] not in self._effective_ids(c,w['owner'],w['kind']):return False
        e=self.commerce._entitlements(c,w['owner'])
        return not w['last_checked'] or parse(w['last_checked'])+timedelta(hours=e['site_scan_hours'] if w['kind']=='SITE' else e['scan_hours'])<=self.s.clock()

    def _catalog_snapshot(self,config,reader=None):
        result=[];seen=set();version=None;offset=0
        for _ in range(100):
            page=(reader or self.core.catalog)(q=config['q'],kind=config['kind'],region=config['region'],offset=offset,limit=50,read_version=version)
            require(isinstance(page,dict) and type(page.get('total')) is int and page['total']<=5000,'主题结果超出本轮安全读取范围；请缩小筛选条件',409,'SCAN_BOUND')
            if version is None:version=page['read_version']
            require(page['read_version']==version,'扫描中目录发生变化，请重试',409,'CATALOG_CHANGED')
            items=page['items'];require(isinstance(items,list) and len(items)<=50,'目录返回格式不正确',502)
            for item in items:
                require(isinstance(item,dict) and isinstance(item.get('id'),str) and item['id'] not in seen,'目录分页重复或内容不完整',502,'INCOMPLETE_SCAN')
                seen.add(item['id']);result.append(item)
            offset+=len(items)
            if not page['has_more']:
                require(offset==page['total'],'目录分页未完整读取',502,'INCOMPLETE_SCAN')
                return result
            require(bool(items) and offset<page['total'],'目录分页没有进展',502,'INCOMPLETE_SCAN')
        raise DomainError('本轮结果未完整读取，请缩小筛选范围',409,'INCOMPLETE_SCAN')

    def scan_topics(self,a):
        a.need('operator');result=dict(checked=0,notices_created=0,failed=0)
        with self.s.read() as c:
            candidates=rows(c,select(watches).where(watches.c.kind=='TOPIC',watches.c.enabled.is_(True)).limit(1000))
            candidates=[w for w in candidates if self._due(c,w)]
        for w in candidates:
            try:
                found=self._catalog_snapshot(w['config'])
                with self.s.write() as c:
                    current=row(c,select(watches).where(watches.c.id==w['id']))
                    if not current or current['version']!=w['version'] or not self._due(c,current):continue
                    created=0
                    deliver=not hasattr(self.core,'notifications_enabled') or self.core.notifications_enabled(c,w['owner'])
                    for item in found if deliver else []:
                        # Only the existing public catalog is consumed; this module cannot publish.
                        key=f"watch:{w['id']}:{item['id']}:{item.get('version','')}:{item.get('status','')}"
                        require(len(key)<=256,'目录标识过长',502)
                        old=row(c,select(notices).where(notices.c.owner==w['owner'],notices.c.key==key))
                        self.s.notice(c,w['owner'],key,str(item.get('title') or '主题机会有更新')[:240],
                            '跟踪主题：'+w['config']['name']+'。'+('来源变化待确认，请查看原机会中的备注。' if item.get('status')=='UPDATE_PENDING' else '此条目匹配你的筛选条件，不代表已判定符合报名资格。'),'opportunity:'+item['id'])
                        created+=int(not old)
                    c.execute(update(watches).where(watches.c.id==w['id']).values(last_checked=self.s.time(),last_error=None))
                result['notices_created']+=created
                result['checked']+=1
            except Exception as exc:
                result['failed']+=1
                with self.s.write() as c:c.execute(update(watches).where(watches.c.id==w['id']).values(last_error=getattr(exc,'code','SCAN_FAILED')))
        return result


    def scan_site_publications(self,a):
        """Separate clocks for source collection and publication delivery."""
        a.need('operator');result=dict(checked=0,notices_created=0,failed=0)
        with self.s.read() as c:
            candidates=rows(c,select(watches).where(watches.c.kind=='SITE',watches.c.enabled.is_(True)).limit(1000))
        for w in candidates:
            try:
                with self.s.read() as c:
                    if w['id'] not in self._effective_ids(c,w['owner'],'SITE'):continue
                    e=self.commerce._entitlements(c,w['owner'])
                    last=w['config'].get('last_catalog_checked')
                    if last and parse(last)+timedelta(hours=e['scan_hours'])>self.s.clock():continue
                    lead=row(c,select(leads).where(leads.c.id==w['config']['lead_id']))
                    if not lead or lead['state']!='APPROVED' or not lead['source_id']:continue
                found=self._catalog_snapshot({'q':'','kind':'','region':''},reader=lambda **kw:self.core.catalog_for_source(lead,**kw))
                with self.s.write() as c:
                    current=row(c,select(watches).where(watches.c.id==w['id']))
                    if not current or current['version']!=w['version'] or w['id'] not in self._effective_ids(c,w['owner'],'SITE'):continue
                    created=0
                    deliver=not hasattr(self.core,'notifications_enabled') or self.core.notifications_enabled(c,w['owner'])
                    for item in found if deliver else []:
                        require(item.get('status') in ('CURRENT','UPDATE_PENDING'),'来源投影包含未公开内容',502,'NON_PUBLIC_ITEM')
                        key=f"site-publication:{w['id']}:{item['id']}:{item.get('version','')}:{item.get('status','')}"
                        require(len(key)<=256,'目录标识过长',502)
                        old=row(c,select(notices).where(notices.c.owner==w['owner'],notices.c.key==key))
                        self.s.notice(c,w['owner'],key,str(item.get('title') or '指定网站有新机会')[:240],
                            '指定网站：'+w['config']['name']+'。'+('来源变化待确认，请查看原机会备注。' if item['status']=='UPDATE_PENDING' else '该机会已进入机会总览；此提醒不是报名资格结论。'),'opportunity:'+item['id'])
                        created+=int(not old)
                    config={**current['config'],'last_catalog_checked':self.s.time()}
                    c.execute(update(watches).where(watches.c.id==w['id']).values(config=config,last_error=None))
                result['checked']+=1;result['notices_created']+=created
            except Exception as exc:
                result['failed']+=1
                with self.s.write() as c:c.execute(update(watches).where(watches.c.id==w['id']).values(last_error=getattr(exc,'code','SOURCE_SCAN_FAILED')))
        return result

    def _lead(self,id):
        with self.s.read() as c:l=row(c,select(leads).where(leads.c.id==id))
        require(l and l['state']=='APPROVED','来源线索尚未通过审核',409,'REVIEW_REQUIRED')
        return l

    def adopt(self,a,lead_id):
        a.need('operator');l=self._lead(lead_id);self.dns(l['approved_url'])
        source=self.core.register(a,l)
        with self.s.write() as c:
            c.execute(update(leads).where(leads.c.id==lead_id).values(source_id=source['id']))
            self.s.audit(c,a.name,'ADOPT_REVIEWED_SOURCE',lead_id,{'source_id':source['id'],'enabled_unchanged':True})
        return source

    def enable_source(self,a,lead_id):
        a.need('operator');l=self._lead(lead_id)
        require(l['source_id'],'请先登记来源',409)
        result=self.core.enable(a,l)
        with self.s.write() as c:
            c.execute(update(leads).where(leads.c.id==lead_id).values(collection_enabled=True))
            self.s.audit(c,a.name,'AUTHORIZE_SOURCE_ENABLE',lead_id)
        return result

    def prepare(self,a,watch_id,connection,key):
        a.need('operator');require(isinstance(connection,str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',connection),'执行连接标识不正确')
        with self.s.write() as c:
            def action():
                w=row(c,select(watches).where(watches.c.id==watch_id));require(w and w['kind']=='SITE','网站跟踪不存在',404)
                require(w['id'] in self._effective_ids(c,w['owner'],'SITE'),'服务未生效、已到期或跟踪已暂停',409,'ENTITLEMENT_REQUIRED')
                old=row(c,select(jobs).where(jobs.c.watch_id==watch_id,jobs.c.state.in_(ACTIVE_JOBS)))
                if old:
                    require(old['connection']==connection and old['actor']==a.name,'该跟踪已有另一执行连接或维护员授权的任务',409)
                    return old
                require(self._due(c,w),'尚未到下一次检查时间',409,'NOT_DUE')
                j=dict(id=uid(),watch_id=watch_id,owner=w['owner'],state='QUEUED',actor=a.name,connection=connection,lease_until=None,attempts=0,generation=0,core_task_id=None,error=None,created_at=self.s.time(),updated_at=self.s.time())
                c.execute(insert(jobs).values(**j));self.s.audit(c,a.name,'AUTHORIZE_SITE_JOB',j['id'],{'watch_id':watch_id,'connection':connection})
                return j
            return self.s.idempotent(c,a.name,'prepare_job',key,dict(watch_id=watch_id,connection=connection),action)

    def list_jobs(self,a,manage=False):
        if manage:a.need('operator')
        with self.s.read() as c:
            q=select(jobs).order_by(jobs.c.created_at.desc()).limit(200)
            if not manage:q=q.where(jobs.c.owner==a.name)
            return rows(c,q)

    def dispatch(self,a,id):
        a.need('operator')
        with self.s.write() as c:
            j=row(c,select(jobs).where(jobs.c.id==id));require(j,'任务不存在',404)
            require(j['actor']==a.name,'请由原授权维护员重试该任务，避免改变任务身份',403)
            if j['state'] not in ('QUEUED','RETRYABLE','DISPATCHING'):return j
            require(j['state']!='DISPATCHING' or j['lease_until']<=self.s.time(),'任务正被处理，请稍后刷新',409,'JOB_LEASED')
            w=row(c,select(watches).where(watches.c.id==j['watch_id']))
            if w['id'] not in self._effective_ids(c,w['owner'],'SITE'):
                c.execute(update(jobs).where(jobs.c.id==id).values(state='BLOCKED',error='ENTITLEMENT_REQUIRED',updated_at=self.s.time()))
                return row(c,select(jobs).where(jobs.c.id==id))
            l=row(c,select(leads).where(leads.c.id==w['config']['lead_id']))
            require(l and l['state']=='APPROVED' and l['source_id'],'请先审核并登记来源',409)
            require(l['collection_enabled'],'请先明确授权本模块使用此来源；原来源默认启用不等于用户定制任务授权',409,'SOURCE_NOT_AUTHORIZED')
            generation=j['generation']+1
            c.execute(update(jobs).where(jobs.c.id==id).values(state='DISPATCHING',generation=generation,attempts=j['attempts']+1,lease_until=stamp(self.s.clock()+timedelta(minutes=2)),updated_at=self.s.time()))
        # External calls intentionally outside the short DB transaction. A stable
        # core request key recovers ambiguous success without issuing another task.
        try:
            self.dns(l['approved_url'])
            task=self.core.enqueue(a,l,'mbr:'+id,j['connection'])
            require(isinstance(task,dict) and task.get('id'),'采集任务回执无效',502)
            state,error='CORE_QUEUED',None
        except Exception as exc:
            task=None;state,error='RETRYABLE',getattr(exc,'code','DISPATCH_RESULT_UNKNOWN')
        with self.s.write() as c:
            current=row(c,select(jobs).where(jobs.c.id==id))
            if current is None:return {'id':id,'state':'CANCELLED','error':'PERSONAL_DATA_ERASED'}
            if current['generation']!=generation:return current
            c.execute(update(jobs).where(jobs.c.id==id).values(state=state,error=error,core_task_id=task['id'] if task else None,lease_until=None,updated_at=self.s.time()))
            if task:c.execute(update(watches).where(watches.c.id==w['id']).values(last_checked=self.s.time(),last_error=None))
            self.s.audit(c,a.name,'SITE_JOB_DISPATCH_RESULT',id,{'state':state,'core_task_id':task['id'] if task else None,'error':error})
            return row(c,select(jobs).where(jobs.c.id==id))

    def refresh(self,a,id):
        a.need('operator')
        with self.s.read() as c:j=row(c,select(jobs).where(jobs.c.id==id))
        require(j and j['core_task_id'],'没有可查询的采集任务',409)
        task=self.core.task(a,j['core_task_id'])
        mapping={'QUEUED':'CORE_QUEUED','RUNNING':'CORE_RUNNING','RECOVERY_QUEUED':'CORE_RUNNING','READY':'RESULT_PENDING_REVIEW','FAILED':'FAILED','NEEDS_RECOVERY':'NEEDS_RECOVERY','CANCELLED':'CANCELLED'}
        state=mapping.get(task.get('status'),'CORE_STATUS_UNKNOWN')
        if task.get('status')=='READY' and task.get('review_state')=='APPROVED':state='PUBLISHED'
        elif task.get('status')=='READY' and task.get('review_state')=='REJECTED':state='NOT_ADOPTED'
        with self.s.write() as c:
            c.execute(update(jobs).where(jobs.c.id==id).values(state=state,updated_at=self.s.time()))
            if state=='RESULT_PENDING_REVIEW':self.s.notice(c,j['owner'],'job-ready:'+id,'网站调查结果已收到','内容正在等待整体审核；尚不能视为已发布或已核实的机会。','watches')
            return row(c,select(jobs).where(jobs.c.id==id))
