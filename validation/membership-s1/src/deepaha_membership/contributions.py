"""Public-site suggestions are reviewable leads, never publication decisions."""
from datetime import timedelta
from sqlalchemy import select, insert, update, func
from .db import leads, submissions, row, rows, uid, digest
from .commerce import bounded_text
from .periods import stamp
from .urls import canonicalize
from .errors import require

TIERS={'OFFICIAL_PRIMARY','OFFICIAL_AGGREGATOR','TRUSTED_SECONDARY','COMMUNITY_SIGNAL'}

class Contributions:
    def __init__(self,store):self.s=store

    def _view(self,c,item):
        lead=row(c,select(leads).where(leads.c.id==item['lead_id']))
        return {**item,'lead':lead}

    def submit(self,a,name,url,kind,note,consent,key):
        name=bounded_text(name,200,'网站名称');url=canonicalize(url)
        note=bounded_text(note,2000,'补充说明',0)
        require(kind in ('SOURCE','CUSTOM'),'请选择线索建议或定制需求')
        require(consent is True,'请确认提交的是公开网址，并同意用于公开来源建设')
        with self.s.write() as c:
            def action():
                lead=row(c,select(leads).where(leads.c.url_hash==digest(url)))
                if lead:
                    old=row(c,select(submissions).where(submissions.c.owner==a.name,submissions.c.lead_id==lead['id']))
                    if old:return self._view(c,old)
                count=c.execute(select(func.count()).select_from(submissions).where(submissions.c.owner==a.name,submissions.c.created_at>=stamp(self.s.clock()-timedelta(days=1)))).scalar()
                require(count<20,'24小时最多提交20个网站，请先查看已有进度',429,'RATE_LIMIT')
                if not lead:
                    lead=dict(id=uid(),url=url,url_hash=digest(url),name=name,state='PENDING',version=1,created_at=self.s.time())
                    c.execute(insert(leads).values(**lead))
                data=dict(id=uid(),owner=a.name,lead_id=lead['id'],kind=kind,note=note,created_at=self.s.time())
                c.execute(insert(submissions).values(**data))
                self.s.audit(c,a.name,'SUBMIT_PUBLIC_SITE',data['id'],{'lead_id':lead['id'],'consent':'public-source-v1'})
                self.s.notice(c,a.name,'submission:'+data['id'],'网站建议已收到','审核通过后可登记为采集来源；当前还不是已发布机会。','feedback')
                return self._view(c,data)
            return self.s.idempotent(c,a.name,'submit_site',key,dict(name=name,url=url,kind=kind,note=note,consent=consent),action)

    def mine(self,a):
        with self.s.read() as c:
            return [self._view(c,x) for x in rows(c,select(submissions).where(submissions.c.owner==a.name).order_by(submissions.c.created_at.desc()).limit(200))]

    def queue(self,a,state=''):
        a.need('reviewer')
        with self.s.read() as c:
            q=select(leads).order_by(leads.c.created_at.desc()).limit(200)
            if state:q=q.where(leads.c.state==state)
            return [{**l,'submissions':rows(c,select(submissions).where(submissions.c.lead_id==l['id']))} for l in rows(c,q)]

    def decide(self,a,id,version,decision,note,public_brief,approved_url,tier,key):
        a.need('reviewer')
        require(decision in ('APPROVE','REJECT','NEEDS_INFO'),'审核结论不正确')
        note=bounded_text(note,1000,'给用户的审核说明',2)
        require(tier in TIERS,'来源类型不正确')
        if decision=='APPROVE':
            public_brief=bounded_text(public_brief,3000,'审核后的公开调查说明',10)
            approved_url=canonicalize(approved_url)
        else:public_brief='';approved_url=None
        data=dict(id=id,version=version,decision=decision,note=note,public_brief=public_brief,approved_url=approved_url,tier=tier)
        with self.s.write() as c:
            def action():
                lead=row(c,select(leads).where(leads.c.id==id));require(lead,'网站线索不存在',404)
                require(lead['version']==version and lead['state'] in ('PENDING','NEEDS_INFO'),'线索状态已变化，请刷新后处理',409,'STALE_VERSION')
                state={'APPROVE':'APPROVED','REJECT':'REJECTED','NEEDS_INFO':'NEEDS_INFO'}[decision]
                c.execute(update(leads).where(leads.c.id==id).values(state=state,version=version+1,decision_note=note,public_brief=public_brief,approved_url=approved_url,tier=tier if decision=='APPROVE' else None))
                self.s.audit(c,a.name,'REVIEW_PUBLIC_SITE',id,{'decision':decision,'version':version+1})
                for sub in rows(c,select(submissions).where(submissions.c.lead_id==id)):
                    self.s.notice(c,sub['owner'],f'lead:{id}:{version+1}','网站建议审核有新进展',note,'feedback')
                return row(c,select(leads).where(leads.c.id==id))
            return self.s.idempotent(c,a.name,'review_site',key,data,action)

    def supplement(self,a,id,version,note,key):
        note=bounded_text(note,2000,'补充说明',5)
        with self.s.write() as c:
            def action():
                sub=row(c,select(submissions).where(submissions.c.id==id,submissions.c.owner==a.name));require(sub,'提交记录不存在',404)
                lead=row(c,select(leads).where(leads.c.id==sub['lead_id']))
                require(lead['version']==version and lead['state'] in ('PENDING','NEEDS_INFO'),'该线索不能修改，请刷新查看结果',409,'STALE_VERSION')
                c.execute(update(submissions).where(submissions.c.id==id).values(note=note))
                c.execute(update(leads).where(leads.c.id==lead['id']).values(state='PENDING',version=version+1))
                self.s.audit(c,a.name,'SUPPLEMENT_SITE',id)
                return self._view(c,row(c,select(submissions).where(submissions.c.id==id)))
            return self.s.idempotent(c,a.name,'supplement_site',key,{'id':id,'version':version,'note':note},action)
