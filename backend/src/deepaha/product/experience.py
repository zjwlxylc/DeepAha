"""Small, additive user/operations queries. All writes retain the domain transaction lock."""
from sqlalchemy import select, func, or_, and_, exists
from .models import (Account, CatalogTarget, Source, SourceProfile, Task, PreparationItem,
                     TargetNotice, Notice, now)
from .errors import Problem
from .auth import aware

TASK_STATES={'QUEUED','RUNNING','RECOVERY_QUEUED','NEEDS_RECOVERY','FAILED','READY','CANCELLED'}
OPEN_STATES={'QUEUED','RUNNING','RECOVERY_QUEUED'}
ISSUE_STATES={'NEEDS_RECOVERY','FAILED'}


def task_guidance(t):
    if t.status=='READY':return {'kind':'OPEN_REVIEW','label':'打开审核','reason':'文件已接收，等待整体审核' if t.revision_id else '接收记录待核查'}
    if t.status in ISSUE_STATES:
        if t.error_code in ('SOURCE_POLICY_CHANGED','BINDING_CHANGED'):
            return {'kind':'NEW_TASK','label':'按新配置另建调查','reason':'授权或执行绑定已变化；旧任务不会自动重发'}
        if t.session_id or all(k in (t.files or {}) for k in ('report.md','opportunities.json','evidence.json')):
            return {'kind':'RECOVER_FILES','label':'继续回收已有文件','reason':'只回收，不重新发送调查'}
        return {'kind':'INSPECT','label':'查看中断记录','reason':'暂无可恢复会话；核查远端后再决定是否另建调查'}
    if t.status=='CANCELLED':return {'kind':'NONE','label':'本地已停止','reason':'远端已经收到的调查不保证停止'}
    return {'kind':'WAIT','label':'等待处理','reason':{'QUEUED':'等待调度；不会重复发送','RUNNING':'调查或文件回收正在进行','RECOVERY_QUEUED':'等待回收已有文件，不发送新调查'}.get(t.status,'请检查记录')}


class ExperienceMixin:
    def search_sources(self,*,actor,q='',enabled=None,health='',offset=0,limit=30):
        if len(q)>300 or not 1<=limit<=50 or offset<0:raise Problem('查询范围不正确')
        if health not in ('','ISSUES','NEVER','OK'):raise Problem('来源健康筛选不正确')
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            cond=[]
            if q:cond.append(or_(Source.authority_name.contains(q,autoescape=True),Source.canonical_url.contains(q,autoescape=True)))
            if enabled is True:cond.append(and_(Source.active.is_(True),SourceProfile.scheduling_enabled.is_(True)))
            if enabled is False:cond.append(or_(Source.active.is_(False),SourceProfile.scheduling_enabled.is_(False),SourceProfile.source_id.is_(None)))
            issues=exists(select(Task.id).where(Task.source_id==Source.source_id,Task.status.in_(ISSUE_STATES)))
            if health=='ISSUES':cond.append(issues)
            if health=='NEVER':cond.append(SourceProfile.last_success.is_(None))
            if health=='OK':cond.extend([SourceProfile.last_success.is_not(None),~issues])
            stmt=select(Source).outerjoin(SourceProfile,Source.source_id==SourceProfile.source_id).where(*cond)
            total=s.scalar(select(func.count()).select_from(stmt.subquery()))
            rows=s.scalars(stmt.order_by(Source.authority_name,Source.source_id).offset(offset).limit(limit))
            items=[]
            for row in rows:
                counts=dict(s.execute(select(Task.status,func.count()).where(Task.source_id==row.source_id).group_by(Task.status)).all())
                data=self._source(s,row.source_id)
                p=s.get(SourceProfile,row.source_id)
                data.update(task_counts=counts,next_due=aware(p.next_due).isoformat() if p and p.next_due else None,
                            health='ISSUES' if any(counts.get(k) for k in ISSUE_STATES) else 'OK' if data['last_success'] else 'NEVER')
                items.append(data)
            return {'items':items,'total':total,'offset':offset,'limit':limit,'has_more':offset+len(items)<total}

    def source_detail(self,id,*,actor):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator');result=self._source(s,id)
            p=s.get(SourceProfile,id)
            result['next_due']=aware(p.next_due).isoformat() if p and p.next_due else None
            result['task_counts']=dict(s.execute(select(Task.status,func.count()).where(Task.source_id==id).group_by(Task.status)).all())
            result['latest_tasks']=[{**self._task_view(t),'next_action':task_guidance(t)} for t in s.scalars(select(Task).where(Task.source_id==id).order_by(Task.created_at.desc(),Task.id).limit(5))]
            return result

    def search_tasks(self,*,actor,q='',status='',source_id='',offset=0,limit=30):
        if len(q)>300 or not 1<=limit<=50 or offset<0 or (status and status not in TASK_STATES):raise Problem('任务筛选不正确')
        with self.db.tx(False) as s:
            self._account(s,actor,'operator');cond=[]
            if q:cond.append(or_(Task.notice_url.contains(q,autoescape=True),Task.instruction.contains(q,autoescape=True),Source.authority_name.contains(q,autoescape=True)))
            if source_id:cond.append(Task.source_id==source_id)
            base=select(Task).join(Source,Source.source_id==Task.source_id).where(*cond)
            counts=dict(s.execute(select(Task.status,func.count()).join(Source,Source.source_id==Task.source_id).where(*cond).group_by(Task.status)).all())
            if status:base=base.where(Task.status==status)
            total=s.scalar(select(func.count()).select_from(base.subquery()))
            items=[]
            for t in s.scalars(base.order_by(Task.created_at.desc(),Task.id).offset(offset).limit(limit)):
                source=s.get(Source,t.source_id)
                items.append({**self._task_view(t),'source_name':source.authority_name,'next_action':task_guidance(t)})
            return {'items':items,'total':total,'counts':counts,'offset':offset,'limit':limit,'has_more':offset+len(items)<total}

    def _item_view(self,row,current=None):
        return {'id':row.id,'target_id':row.target_public_id,'text':row.text,'done':row.done,'origin':row.origin,
                'publication_id':row.publication_id,'field_id':row.field_id,'version':row.version,
                'material_changed':bool(current and current.publication_id!=row.publication_id),
                'created_at':aware(row.created_at).isoformat(),'updated_at':aware(row.updated_at).isoformat()}

    def preparation_items(self,target_id=None,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor);stmt=select(PreparationItem).where(PreparationItem.account_id==a.id)
            if target_id:stmt=stmt.where(PreparationItem.target_public_id==target_id)
            # Export has no UI limit, and remains private to the owning account.
            current=self._current_target(s,target_id) if target_id else None
            items=[self._item_view(x,current) for x in s.scalars(stmt.order_by(PreparationItem.created_at,PreparationItem.id))]
            return {'items':items,'total':len(items),'target_available':bool(current) if target_id else None}

    def add_preparation_item(self,target_id,*,actor,text,request_key,field_id=None):
        if not isinstance(text,str) or not text.strip() or len(text)>500:raise Problem('请填写1至500字的准备事项')
        if not isinstance(request_key,str) or not 1<=len(request_key)<=128:raise Problem('请求标识不正确')
        with self.db.tx() as s:
            a=self._account(s,actor)
            old=s.scalar(select(PreparationItem).where(PreparationItem.account_id==a.id,PreparationItem.request_key==request_key))
            if old:
                if old.target_public_id!=target_id or old.text!=text.strip() or old.field_id!=field_id:raise Problem('该请求已用于其他事项',409,'REQUEST_CONFLICT')
                return self._item_view(old)
            target=self._target_row(s,target_id)
            if s.scalar(select(func.count()).select_from(PreparationItem).where(PreparationItem.account_id==a.id,PreparationItem.target_public_id==target_id))>=100:
                raise Problem('每项机会最多保存100个准备事项',409,'ITEM_LIMIT')
            # A browser cannot claim official provenance. Optional copied fields must match saved content.
            origin='USER'
            if field_id:
                body=target.content or {};fields=[]
                for key in ('fields','common_fields','ancestor_fields'):fields.extend(body.get(key,[]))
                f=next((x for x in fields if x.get('id')==field_id),None)
                if not f or f.get('excluded') or str(f.get('value','')).strip()!=text.strip():raise Problem('该材料内容已变化或不能作为准备参考',409,'MATERIAL_CHANGED')
                origin='OFFICIAL_SUGGESTION'
            row=PreparationItem(account_id=a.id,target_public_id=target_id,text=text.strip(),request_key=request_key,
                publication_id=target.publication_id,field_id=field_id,origin=origin)
            s.add(row);s.flush();return self._item_view(row,target)

    def update_preparation_item(self,target_id,id,*,actor,expected_version,text=None,done=None,remove=False):
        if type(expected_version) is not int or expected_version<1:raise Problem('事项版本不正确')
        if text is not None and (not isinstance(text,str) or not text.strip() or len(text)>500):raise Problem('事项内容不正确')
        if done is not None and type(done) is not bool:raise Problem('完成状态不正确')
        with self.db.tx() as s:
            a=self._account(s,actor);r=s.get(PreparationItem,id)
            if not r or r.account_id!=a.id or r.target_public_id!=target_id:raise Problem('事项不存在',404)
            if r.version!=expected_version:raise Problem('事项已更新，请刷新清单后再操作',409,'ITEM_CHANGED')
            if remove:s.delete(r);return {'removed':True}
            if text is not None:
                r.text=text.strip();r.origin='USER';r.field_id=None
            if done is not None:r.done=done
            r.version+=1;r.updated_at=now()
            return self._item_view(r,self._current_target(s,target_id))

    def mark_notifications(self,ids,*,actor):
        if not isinstance(ids,list) or len(ids)>100 or any(not isinstance(x,str) for x in ids):raise Problem('消息标识不正确')
        with self.db.tx() as s:
            a=self._account(s,actor);rows=[]
            membership_ids=[]
            for id in set(ids):
                if id.startswith('mbr:'):
                    from .membership import mark_notice
                    mark_notice(s.connection(),actor,id)
                    membership_ids.append(id)
                    continue
                r=s.get(TargetNotice,id) or s.get(Notice,id)
                if not r or r.account_id!=a.id:raise Problem('消息不存在',404)
                rows.append(r)
            for r in rows:
                if r.state!='CANCELLED' and aware(r.due_at)<=now():r.state='READ'
            return {'read':True,'count':sum(r.state=='READ' for r in rows)+len(membership_ids)}
