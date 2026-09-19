import copy
import json
from sqlalchemy import select, func, cast, Text, or_
from .models import Snapshot, Revision, Decision, Publication, SourceProfile, Opportunity, Identity, Notice, Action, CatalogTarget, TargetNotice, TargetAction, now, uid
from .adapter import project, public_content, hash_json
from .catalog_projection import materialize_catalog_targets
from .currentness import analyze_changes, apply_pending_currentness, affected_deadline
from .storage import unpack, sha
from .errors import Problem

class IntakeMixin:
    def ingest(self,source_id,archive,*,actor,task_id=None,notice_url=None):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator');source=self._source(s,source_id)
        files=unpack(archive)
        digest=hash_json({k:sha(v) for k,v in sorted(files.items())})
        with self.db.tx(False) as s:
            old=s.scalar(select(Snapshot).where(Snapshot.source_id==source_id,Snapshot.digest==digest))
            if old:
                rev=s.scalar(select(Revision).where(Revision.snapshot_id==old.id))
                if rev:return self._preview(s,rev)
        manifest=self.store.save(files)
        # Immutable raw archive is retained separately from normalized entry identities.
        manifest['__received_archive.zip']=self.store.save({'__received_archive.zip':archive})['__received_archive.zip']
        with self.db.tx() as s:
            old=s.scalar(select(Snapshot).where(Snapshot.source_id==source_id,Snapshot.digest==digest))
            if old:snap_id=old.id
            else:
                snap=Snapshot(source_id=source_id,digest=digest,manifest=manifest,task_id=task_id)
                s.add(snap);s.flush();snap_id=snap.id
                self._audit(s,actor,'RECEIVE_RESULT',snap_id,'原始文件已保存')
        # A parsing failure cannot roll back receipt/raw bytes.
        try:content=project(files,source,notice_url)
        except (Problem,ValueError,TypeError,RecursionError) as e:
            content={'adapter_version':'overview-display/3.0.0','opportunities':[],'artifacts':[],
             'notes':[],'blockers':['内容整理未完成，原始文件已保存。'],'can_approve':False,'field_count':0,
             'report':files.get('report.md',b'').decode('utf-8',errors='replace')[:200000]}
        # SG3 compares the pending projection with the accepted target frontier before
        # any approval.  Generate the revision id first so weak identities remain scoped
        # to this exact return without mutating OpportunityUnit rows.
        rev_id=uid()
        with self.db.tx() as s:
            old=s.scalar(select(Revision).where(Revision.snapshot_id==snap_id))
            if old:return self._preview(s,old)
            any_currentness_change=False
            for item in content['opportunities']:
                ident=s.scalar(select(Identity).where(Identity.source_id==source_id,Identity.source_key==item['identity_key']))
                if not ident:continue
                opp=s.get(Opportunity,ident.opportunity_id)
                old_pub=s.scalar(select(Publication).where(
                    Publication.opportunity_id==ident.opportunity_id,
                    Publication.status.in_(['CURRENT','UPDATE_PENDING'])
                ).order_by(Publication.created_at.desc(),Publication.id.desc()))
                if not old_pub:continue
                old_rev=s.get(Revision,old_pub.revision_id)
                summary=analyze_changes(
                    s,opp,old_pub,old_rev.content if old_rev else {},content,item,content['notes'],rev_id
                )
                item['currentness']=summary
                if summary['has_changes'] or summary.get('replaced_artifacts'):
                    any_currentness_change=True
            p_hash=hash_json({'content':content,'snapshot':digest,'source_policy':source['policy_version']})
            rev=Revision(id=rev_id,snapshot_id=snap_id,preview_hash=p_hash,content=content,
                         can_approve=content['can_approve'],policy_version=source['policy_version'])
            s.add(rev);s.flush()
            # Pending invalidation is target-scoped.  Stored old values remain intact;
            # read projection decides which affected usages must be hidden.
            for item in content['opportunities']:
                summary=item.get('currentness')
                if not summary:continue
                ident=s.scalar(select(Identity).where(Identity.source_id==source_id,Identity.source_key==item['identity_key']))
                if not ident:continue
                opp=s.get(Opportunity,ident.opportunity_id)
                old_pub=s.scalar(select(Publication).where(
                    Publication.opportunity_id==ident.opportunity_id,
                    Publication.status.in_(['CURRENT','UPDATE_PENDING'])
                ).order_by(Publication.created_at.desc(),Publication.id.desc()))
                applied=apply_pending_currentness(s,opp,summary,rev.id)
                if summary['has_changes'] or summary.get('replaced_artifacts'):
                    if old_pub:old_pub.status='UPDATE_PENDING'
                    for change in applied:
                        self._target_change_notice(s,opp.opportunity_id,change,rev.id,cancel_deadline=affected_deadline(change))
            if any_currentness_change:self.db.tick(s)
            self._audit(s,actor,'PREPARE_OVERVIEW',rev.id,'形成完整内容预览、变更范围与关联备注')
            return self._preview(s,rev)
    def _preview(self,s,rev):
        snap=s.get(Snapshot,rev.snapshot_id)
        d=s.scalar(select(Decision).where(Decision.revision_id==rev.id))
        body=copy.deepcopy(rev.content)
        body.update({'id':rev.id,'preview_hash':rev.preview_hash,'status':rev.status,
           'source':self._source(s,snap.source_id),'received_at':snap.received_at.isoformat(),
           'receipt':d.receipt if d else None,'overall_note':d.note if d else '',
           'file_names':[k for k in snap.manifest if k!='__received_archive.zip']})
        return body
    def preview(self,id,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            if not set(a.roles)&{'reviewer','operator'}:raise Problem('没有读取审核内容的权限',403)
            r=s.get(Revision,id)
            if not r:raise Problem('审核结果不存在',404)
            return self._preview(s,r)
    def inbox(self,*,actor,status='PENDING',q='',offset=0,limit=30):
        with self.db.tx(False) as s:
            self._account(s,actor,'reviewer')
            stmt=select(Revision).order_by(Revision.created_at.desc(),Revision.id.desc())
            if status!='ALL':stmt=stmt.where(Revision.status==status)
            if q:
                col=func.lower(cast(Revision.content['opportunities'],Text))
                literal=q.casefold(); escaped=json.dumps(literal,ensure_ascii=True)[1:-1]
                stmt=stmt.where(or_(col.contains(literal,autoescape=True),col.contains(escaped,autoescape=True)))
            total=s.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            rows=[]
            for r in s.scalars(stmt.offset(offset).limit(min(limit,50))):
                snap=s.get(Snapshot,r.snapshot_id);src=self._source(s,snap.source_id)
                rows.append({'id':r.id,'title':' / '.join(x['title'] for x in r.content['opportunities']) or '未完成的返回结果',
                 'status':r.status,'can_approve':r.can_approve,'count':len(r.content['opportunities']),
                 'field_count':r.content['field_count'],'source':src['name'],'received_at':snap.received_at.isoformat(),
                 'notes':len(r.content['notes'])+sum(len(x['notes']) for x in r.content['opportunities']),
                 'blockers':r.content['blockers']})
            return {'items':rows,'total':total,'offset':offset}
    def decide(self,id,decision,preview_hash,note,request_key,*,actor):
        if decision not in ('APPROVE','REJECT'):raise Problem('决定只能是通过或不通过')
        if not isinstance(note,str) or len(note)>3000:raise Problem('整体备注过长')
        if decision=='REJECT' and not note.strip():raise Problem('请填写一个整体不通过原因')
        if not 8<=len(request_key)<=128:
            # Short local test keys are also accepted but never empty.
            if not request_key or len(request_key)>128:raise Problem('请求标识不正确')
        with self.db.tx() as s:
            a=self._account(s,actor,'reviewer')
            old=s.scalar(select(Decision).where(Decision.reviewer_id==a.id,Decision.request_key==request_key))
            if old:
                if (old.revision_id,old.decision,old.preview_hash,old.note)!=(id,decision,preview_hash,note):raise Problem('请求标识已用于另一项决定',409,'IDEMPOTENCY_CONFLICT')
                return old.receipt
            rev=s.get(Revision,id)
            if not rev:raise Problem('审核结果不存在',404)
            existing=s.scalar(select(Decision).where(Decision.revision_id==id))
            if existing:raise Problem('此版本已有整体决定，请读取已保存的结果',409,'ALREADY_DECIDED')
            if rev.preview_hash!=preview_hash:raise Problem('预览版本已变化，请刷新后决定',409,'STALE_PREVIEW')
            snap=s.get(Snapshot,rev.snapshot_id);source=self._source(s,snap.source_id)
            if source['policy_version']!=rev.policy_version:raise Problem('来源使用范围已变化，需重新整理预览',409,'SOURCE_POLICY_CHANGED')
            if decision=='APPROVE' and not rev.can_approve:raise Problem('这份结果不能可靠收录，请查看整体原因',409,'NOT_ADMISSIBLE')
            # A newer received version cannot be silently replaced by approving
            # an older pending screen, even before either version is published.
            if decision=='APPROVE':
                for item in rev.content['opportunities']:
                    newer=select(Revision).join(Snapshot,Revision.snapshot_id==Snapshot.id).where(
                        Snapshot.source_id==snap.source_id,
                        or_(Revision.created_at>rev.created_at,
                            (Revision.created_at==rev.created_at)&(Revision.id>rev.id)),
                        cast(Revision.content['opportunities'],Text).contains(item['identity_key']))
                    for candidate in s.scalars(newer):
                        if any(x['identity_key']==item['identity_key'] for x in candidate.content['opportunities']):
                            raise Problem('此机会已有较新的返回，请审核最新版本',409,'OLDER_REVISION')
            # Superseded source content cannot become current through an old preview.
            for item in rev.content['opportunities']:
                ident=s.scalar(select(Identity).where(Identity.source_id==snap.source_id,Identity.source_key==item['identity_key']))
                if ident:
                    latest=s.scalar(select(Publication).where(Publication.opportunity_id==ident.opportunity_id).order_by(Publication.created_at.desc(),Publication.id.desc()))
                    if latest:
                        other=s.get(Revision,latest.revision_id)
                        if other.created_at>rev.created_at:raise Problem('此机会已有较新的收录版本',409,'OLDER_REVISION')
            receipt={'id':uid(),'revision_id':id,'decision':decision,'preview_hash':preview_hash,'public_ids':[],'catalog_target_ids':[], 'saved_at':now().isoformat()}
            d=Decision(id=receipt['id'],revision_id=id,reviewer_id=a.id,request_key=request_key,decision=decision,preview_hash=preview_hash,note=note,receipt=copy.deepcopy(receipt))
            s.add(d);s.flush()
            if decision=='APPROVE':
                for item in rev.content['opportunities']:
                    ident=s.scalar(select(Identity).where(Identity.source_id==snap.source_id,Identity.source_key==item['identity_key']))
                    if not ident:
                        oid=uid();opp=Opportunity(opportunity_id=oid,public_id='opp_'+oid.replace('-',''),type=item['type'],canonical_title=item['title'],issuer_name=item['issuer'],jurisdiction=item['region'] or None)
                        s.add(opp);s.flush();ident=Identity(source_id=snap.source_id,source_key=item['identity_key'],opportunity_id=oid);s.add(ident)
                    else:opp=s.get(Opportunity,ident.opportunity_id)
                    for old_pub in s.scalars(select(Publication).where(Publication.opportunity_id==opp.opportunity_id,Publication.status.in_(['CURRENT','UPDATE_PENDING']))):old_pub.status='SUPERSEDED'
                    opp.updated_at=now() # Preserve legacy formal fact/qualification state.
                    root_withdrawn=item.get('lifecycle_status')=='WITHDRAWN'
                    pub=Publication(opportunity_id=opp.opportunity_id,decision_id=d.id,revision_id=id,
                                    content=public_content(item,rev.content['notes']),
                                    status='WITHDRAWN' if root_withdrawn else 'CURRENT')
                    if root_withdrawn:
                        opp.status='WITHDRAWN'
                    s.add(pub);s.flush();receipt['public_ids'].append(opp.public_id)
                    receipt['catalog_target_ids'].extend(materialize_catalog_targets(s,opp,pub,item,rev.content['notes'],product=self))
                self.db.tick(s)
            rev.status='APPROVED' if decision=='APPROVE' else 'REJECTED'
            d.receipt=copy.deepcopy(receipt)
            self._audit(s,actor,'OVERVIEW_'+decision,id,note or '整体收录')
            return receipt
    def _target_change_notice(self,s,oid,change,key,cancel_deadline=False):
        public_id=change.get('public_id')
        if not public_id:return
        if cancel_deadline:
            for n in s.scalars(select(TargetNotice).where(
                TargetNotice.target_public_id==public_id,TargetNotice.kind=='DEADLINE',TargetNotice.state!='CANCELLED'
            )):n.state='CANCELLED'
        body=change.get('summary') or '这项具体机会有新的官方内容等待确认。'
        for action in s.scalars(select(TargetAction).where(TargetAction.opportunity_id==oid,TargetAction.target_public_id==public_id)):
            profile=self._profile(s,action.account_id)
            if profile.get('notification_enabled') is False or profile.get('notification_change_enabled') is False:continue
            dedupe='target-currentness:'+public_id+':'+str(key)
            if not s.scalar(select(TargetNotice).where(TargetNotice.account_id==action.account_id,TargetNotice.dedupe_key==dedupe)):
                s.add(TargetNotice(account_id=action.account_id,target_public_id=public_id,opportunity_id=oid,
                    title='关注的具体机会有更新',body=body,kind='CHANGE',dedupe_key=dedupe))

    def _invalidate_notices(self,s,oid,body,key):
        for n in s.scalars(select(Notice).where(Notice.opportunity_id==oid,Notice.kind=='DEADLINE',Notice.state!='CANCELLED')):n.state='CANCELLED'
        for n in s.scalars(select(TargetNotice).where(TargetNotice.opportunity_id==oid,TargetNotice.kind=='DEADLINE',TargetNotice.state!='CANCELLED')):n.state='CANCELLED'
        for action in s.scalars(select(Action).where(Action.opportunity_id==oid)):
            profile=self._profile(s,action.account_id)
            if profile.get('notification_enabled') is False or profile.get('notification_change_enabled') is False:continue
            dedupe='change:'+key
            if not s.scalar(select(Notice).where(Notice.account_id==action.account_id,Notice.dedupe_key==dedupe)):
                s.add(Notice(account_id=action.account_id,opportunity_id=oid,title='关注的机会有变化',body=body,dedupe_key=dedupe))
        for action in s.scalars(select(TargetAction).where(TargetAction.opportunity_id==oid)):
            profile=self._profile(s,action.account_id)
            if profile.get('notification_enabled') is False or profile.get('notification_change_enabled') is False:continue
            dedupe='target-change:'+action.target_public_id+':'+key
            if not s.scalar(select(TargetNotice).where(TargetNotice.account_id==action.account_id,TargetNotice.dedupe_key==dedupe)):
                s.add(TargetNotice(account_id=action.account_id,target_public_id=action.target_public_id,opportunity_id=oid,title='关注的具体机会有变化',body=body,dedupe_key=dedupe))
    def withdraw(self,public_id,reason,*,actor,expected_publication=None):
        if not reason.strip():raise Problem('请填写撤回原因')
        with self.db.tx() as s:
            self._account(s,actor,'reviewer')
            # Root announcement withdrawal keeps the legacy whole-opportunity
            # behavior.  A target id, however, withdraws only that actionable
            # unit and must not remove its siblings.
            opp=s.scalar(select(Opportunity).where(Opportunity.public_id==public_id))
            if opp:
                pubs=list(s.scalars(select(Publication).where(
                    Publication.opportunity_id==opp.opportunity_id,
                    Publication.status.in_(['CURRENT','UPDATE_PENDING'])
                ).order_by(Publication.created_at.desc(),Publication.id.desc())))
                if expected_publication and pubs and pubs[0].id!=expected_publication:
                    raise Problem('内容版本已变化，请刷新',409)
                for p in pubs:p.status='WITHDRAWN'
                for target in s.scalars(select(CatalogTarget).where(
                    CatalogTarget.opportunity_id==opp.opportunity_id,
                    CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])
                )):target.status='WITHDRAWN'
                opp.status='WITHDRAWN'
                self._invalidate_notices(s,opp.opportunity_id,'此机会已撤回，原行动提醒已取消。',uid())
                self.db.tick(s);self._audit(s,actor,'WITHDRAW',public_id,reason[:3000])
                return {'id':public_id,'status':'WITHDRAWN','scope':'ROOT'}

            target=s.scalar(select(CatalogTarget).where(
                CatalogTarget.public_id==public_id,
                CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])
            ).order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc()))
            if not target:raise Problem('机会不存在',404)
            if expected_publication and target.publication_id!=expected_publication:
                raise Problem('内容版本已变化，请刷新',409)
            target.status='WITHDRAWN'
            for notice in s.scalars(select(TargetNotice).where(
                TargetNotice.target_public_id==public_id,
                TargetNotice.kind=='DEADLINE',TargetNotice.state!='CANCELLED'
            )):notice.state='CANCELLED'
            change={'public_id':public_id,'summary':'此具体机会已撤回，原行动提醒已取消。'}
            self._target_change_notice(s,target.opportunity_id,change,uid(),cancel_deadline=False)
            self.db.tick(s);self._audit(s,actor,'WITHDRAW_TARGET',public_id,reason[:3000])
            return {'id':public_id,'status':'WITHDRAWN','scope':'TARGET'}
    def raw_file(self,id,name,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            if not set(a.roles)&{'reviewer','operator'}:raise Problem('没有读取原件的权限',403)
            r=s.get(Revision,id)
            if not r:raise Problem('记录不存在',404)
            snap=s.get(Snapshot,r.snapshot_id)
            return self.store.one(snap.manifest,name)
