import copy
import json
from collections import Counter, defaultdict
from sqlalchemy import select, func, cast, Text, or_
from .models import Publication, Opportunity, Meta, CatalogTarget
from .currentness import diff_target_content
from .errors import Problem


class CatalogMixin:
    def _public(self, s, p, opp):
        """Root announcement projection retained for review/history compatibility."""
        c = copy.deepcopy(p.content)
        c.update({'id':opp.public_id,'publication_id':p.id,'version':p.revision_id,'status':p.status,'updated_at':p.created_at.isoformat()})
        if p.status == 'UPDATE_PENDING':
            c['notes'] = list(dict.fromkeys(c.get('notes', []) + ['来源有更新，受影响内容等待收录。']))
            c['deadline'] = None;c['deadline_precision'] = None
        return c

    def _target(self, target, opp):
        c = copy.deepcopy(target.content)
        c.update({
            'id':target.public_id,
            'catalog_target_id':target.id,
            'publication_id':target.publication_id,
            'version':target.revision_id,
            'status':target.status,
            'updated_at':target.created_at.isoformat(),
            'root_public_id':c.get('root_public_id') or opp.public_id,
        })
        if target.status == 'UPDATE_PENDING':
            currentness = c.get('currentness') if isinstance(c.get('currentness'), dict) else {}
            affected = set(currentness.get('affected_fields') or ())
            c['notes'] = list(dict.fromkeys(c.get('notes', []) + [
                currentness.get('summary') or '来源有更新或本次返回覆盖不完整，请以详情中的备注为准。'
            ]))
            # A pending change only disables usages that are actually affected.
            # Do not erase an unrelated sibling field merely because the source
            # returned a newer package.
            if 'deadline' in affected or currentness.get('change_kind') in {'MISSING_PENDING','WITHDRAWAL_PENDING'}:
                c['deadline'] = None;c['deadline_precision'] = None
            for scope in ('fields','ancestor_fields','common_fields'):
                rows = c.get(scope) if isinstance(c.get(scope), list) else []
                counts = {}
                for field in rows:
                    if not isinstance(field, dict):
                        continue
                    label = str(field.get('label') or '未命名字段')
                    counts[label] = counts.get(label, 0) + 1
                    key = f'{scope}:{label}#{counts[label]}'
                    if key not in affected:
                        continue
                    field['notes'] = list(dict.fromkeys(list(field.get('notes') or []) + ['来源有更新，此值等待收录。']))
                    usage = dict(field.get('usage') or {})
                    usage.update({'qualification':False,'date_action':False})
                    field['usage'] = usage
        return c

    def _current_target(self, s, public_id):
        row=s.scalar(
            select(CatalogTarget)
            .where(CatalogTarget.public_id == public_id, CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
            .order_by(CatalogTarget.created_at.desc(), CatalogTarget.id.desc())
        )
        if row:return row
        # Compatibility only: an old root public id may address exactly one actionable target.
        # Multi-unit roots are deliberately not guessed.
        opp=s.scalar(select(Opportunity).where(Opportunity.public_id==public_id))
        if not opp:return None
        rows=list(s.scalars(select(CatalogTarget).where(CatalogTarget.opportunity_id==opp.opportunity_id,CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc()).limit(2)))
        return rows[0] if len(rows)==1 else None

    def catalog(self, q='', kind='', region='', offset=0, limit=20, read_version=None):
        if offset < 0 or not 1 <= limit <= 50:raise Problem('分页参数不正确')
        with self.db.tx(False) as s:
            version = int(s.get(Meta,'catalog_revision').value)
            if read_version is not None and int(read_version) != version:
                raise Problem('机会列表已有更新，请重新读取',409,'CATALOG_CHANGED')
            stmt = (
                select(CatalogTarget, Opportunity)
                .join(Opportunity, CatalogTarget.opportunity_id == Opportunity.opportunity_id)
                .where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
                .order_by(CatalogTarget.created_at.desc(), CatalogTarget.id.desc())
            )
            if kind:
                stmt = stmt.where(CatalogTarget.content['type'].as_string() == kind)
            if q:
                literal = q.casefold(); escaped = json.dumps(literal, ensure_ascii=True)[1:-1]
                col = func.lower(cast(CatalogTarget.content, Text))
                stmt = stmt.where(or_(col.contains(literal,autoescape=True), col.contains(escaped,autoescape=True)))
            if region:
                location = CatalogTarget.content['region'].as_string()
                stmt = stmt.where(or_(location.contains(region,autoescape=True), location=='', location.is_(None)))
            total = s.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            selected = [self._target(t,o) for t,o in s.execute(stmt.offset(offset).limit(limit))]
            keys = ['id','title','type','issuer','source_name','official_url','region','summary','notes','deadline',
                    'deadline_precision','eligibility','status','version','publication_id','updated_at','target_kind',
                    'code','parent_announcement','root_public_id','scope_labels','presentation','application_url','raw_type',
                    'milestones','time_readiness','primary_milestone','deadline_at']
            cards=[]
            for c in selected:
                cards.append({k:c.get(k) for k in keys})
            return {'items':cards,'total':total or 0,'offset':offset,'limit':limit,'read_version':version,'has_more':offset+limit<(total or 0)}


    @staticmethod
    def _time_matches(content, time_state):
        if not time_state:return True
        readiness=content.get('time_readiness') if isinstance(content.get('time_readiness'),dict) else {}
        state=str(readiness.get('state') or 'UNKNOWN')
        action=str(readiness.get('action_state') or 'UNKNOWN')
        if time_state=='NEEDS_ATTENTION':return state in {'PARTIAL','CONFLICT','PENDING_UPDATE','UNKNOWN'}
        if time_state=='CLOSED':return action=='CLOSED'
        return state==time_state

    def _management_rows(self,s):
        return list(s.execute(
            select(CatalogTarget,Opportunity)
            .join(Opportunity,CatalogTarget.opportunity_id==Opportunity.opportunity_id)
            .where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
            .order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc())
        ))

    def catalog_management_summary(self, *, actor):
        with self.db.tx(False) as s:
            self._account(s,actor,'reviewer')
            rows=self._management_rows(s)
            states=Counter();actions=Counter();roots=set();types=Counter()
            for target,opp in rows:
                content=target.content if isinstance(target.content,dict) else {}
                readiness=content.get('time_readiness') if isinstance(content.get('time_readiness'),dict) else {}
                states[str(readiness.get('state') or 'UNKNOWN')]+=1
                actions[str(readiness.get('action_state') or 'UNKNOWN')]+=1
                roots.add(opp.opportunity_id);types[str(content.get('type') or opp.type)]+=1
            attention=sum(states[x] for x in ('PARTIAL','CONFLICT','PENDING_UPDATE','UNKNOWN'))
            return {
                'targets':len(rows),'roots':len(roots),'update_pending':sum(1 for t,_ in rows if t.status=='UPDATE_PENDING'),
                'time_ready':states['READY'],'time_rolling':states['ROLLING'],'time_attention':attention,'closed':actions['CLOSED'],
                'time_states':dict(states),'types':dict(types),
            }

    def catalog_management_groups(self, *, actor, q='', kind='', status='', time_state='', offset=0, limit=20):
        if offset<0 or not 1<=limit<=50:raise Problem('分页参数不正确')
        q=(q or '').strip().casefold()
        with self.db.tx(False) as s:
            self._account(s,actor,'reviewer')
            all_rows=self._management_rows(s);grouped=defaultdict(list);opps={}
            for target,opp in all_rows:
                grouped[opp.opportunity_id].append(target);opps[opp.opportunity_id]=opp
            items=[]
            for oid,targets in grouped.items():
                opp=opps[oid]
                converted=[self._target(t,opp) for t in targets]
                def match(c):
                    if kind and c.get('type')!=kind:return False
                    if status and c.get('status')!=status:return False
                    if time_state and not self._time_matches(c,time_state):return False
                    if q:
                        hay=' '.join([str(opp.canonical_title or ''),str(opp.issuer_name or ''),str(c.get('title') or ''),str(c.get('code') or '')]).casefold()
                        if q not in hay:return False
                    return True
                root_match=not q or q in (' '.join([str(opp.canonical_title or ''),str(opp.issuer_name or '')]).casefold())
                if not root_match and not any(match(c) for c in converted):continue
                if (kind or status or time_state) and not any(match(c) for c in converted):continue
                state_counts=Counter(str((c.get('time_readiness') or {}).get('state') or 'UNKNOWN') for c in converted)
                action_counts=Counter(str((c.get('time_readiness') or {}).get('action_state') or 'UNKNOWN') for c in converted)
                status_counts=Counter(c.get('status') or 'CURRENT' for c in converted)
                deadlines=sorted(c['deadline'] for c in converted if c.get('deadline'))
                attention=sum(state_counts[x] for x in ('PARTIAL','CONFLICT','PENDING_UPDATE','UNKNOWN'))+status_counts['UPDATE_PENDING']
                ordered=sorted(converted,key=lambda c:(c.get('status')!='UPDATE_PENDING',(c.get('time_readiness') or {}).get('state') in {'READY','ROLLING'},c.get('title') or ''))
                items.append({
                    'root_public_id':opp.public_id,'title':opp.canonical_title,'issuer':opp.issuer_name,'type':opp.type,
                    'target_count':len(converted),'status_counts':dict(status_counts),'time_states':dict(state_counts),'action_states':dict(action_counts),
                    'earliest_deadline':deadlines[0] if deadlines else None,'first_collected_at':min(t.created_at for t in targets).isoformat(),
                    'updated_at':max(t.created_at for t in targets).isoformat(),'needs_attention':attention,
                    'sample_targets':[{'id':c['id'],'title':c.get('title'),'code':c.get('code'),'status':c.get('status'),'deadline':c.get('deadline'),
                                       'time_readiness':c.get('time_readiness')} for c in ordered[:5]],
                })
            items.sort(key=lambda x:(x['needs_attention']==0,-x['needs_attention'],x['title']))
            total=len(items)
            return {'items':items[offset:offset+limit],'total':total,'offset':offset,'limit':limit,'has_more':offset+limit<total}

    def catalog_management_group_targets(self, root_public_id, *, actor, q='', status='', time_state='', offset=0, limit=20):
        if offset<0 or not 1<=limit<=50:raise Problem('分页参数不正确')
        q=(q or '').strip().casefold()
        with self.db.tx(False) as s:
            self._account(s,actor,'reviewer')
            opp=s.scalar(select(Opportunity).where(Opportunity.public_id==root_public_id))
            if not opp:raise Problem('父公告不存在',404)
            rows=list(s.scalars(select(CatalogTarget).where(
                CatalogTarget.opportunity_id==opp.opportunity_id,CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])
            ).order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc())))
            converted=[]
            for target in rows:
                c=self._target(target,opp)
                if q and q not in (' '.join([str(c.get('title') or ''),str(c.get('issuer') or ''),str(c.get('code') or '')]).casefold()):continue
                if status and c.get('status')!=status:continue
                if time_state and not self._time_matches(c,time_state):continue
                converted.append(c)
            keys=['id','title','type','issuer','code','status','deadline','deadline_precision','deadline_at','updated_at','publication_id','root_public_id','target_kind','time_readiness','primary_milestone','presentation']
            return {'root_public_id':root_public_id,'title':opp.canonical_title,'items':[{k:c.get(k) for k in keys} for c in converted[offset:offset+limit]],
                    'total':len(converted),'offset':offset,'limit':limit,'has_more':offset+limit<len(converted)}

    def catalog_management_targets(self, *, actor, q='', kind='', status='', time_state='', offset=0, limit=50):
        if offset<0 or not 1<=limit<=50:raise Problem('分页参数不正确')
        q=(q or '').strip().casefold()
        with self.db.tx(False) as s:
            self._account(s,actor,'reviewer')
            converted=[]
            for target,opp in self._management_rows(s):
                c=self._target(target,opp)
                if kind and c.get('type')!=kind:continue
                if status and c.get('status')!=status:continue
                if time_state and not self._time_matches(c,time_state):continue
                if q and q not in (' '.join([str(c.get('title') or ''),str(c.get('issuer') or ''),str(c.get('code') or ''),str((c.get('parent_announcement') or {}).get('title') or '')]).casefold()):continue
                converted.append(c)
            keys=['id','title','type','issuer','code','status','deadline','deadline_precision','deadline_at','updated_at','publication_id','root_public_id','target_kind','time_readiness','primary_milestone','parent_announcement','presentation']
            total=len(converted)
            return {'items':[{k:c.get(k) for k in keys} for c in converted[offset:offset+limit]],'total':total,'offset':offset,'limit':limit,'has_more':offset+limit<total}

    def detail(self, public_id):
        with self.db.tx(False) as s:
            # Backward-compatible root lookup: review receipts created before SG1
            # contain the announcement public id.  Keep that id addressing the
            # announcement itself; catalog cards use actionable target ids.
            root_opp = s.scalar(select(Opportunity).where(Opportunity.public_id == public_id))
            if root_opp:
                publication = s.scalar(
                    select(Publication)
                    .where(Publication.opportunity_id == root_opp.opportunity_id,
                           Publication.status.in_(['CURRENT','UPDATE_PENDING']))
                    .order_by(Publication.created_at.desc(), Publication.id.desc())
                )
                if publication:
                    return self._public(s, publication, root_opp)
            target = self._current_target(s, public_id)
            if not target:raise Problem('机会不存在或已撤回',404)
            opp = s.get(Opportunity, target.opportunity_id)
            c = self._target(target, opp)
            siblings = list(s.scalars(
                select(CatalogTarget)
                .where(CatalogTarget.opportunity_id == opp.opportunity_id,
                       CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']),
                       CatalogTarget.public_id != public_id)
                .order_by(CatalogTarget.content['title'].as_string(), CatalogTarget.public_id)
                .limit(20)
            ))
            c['siblings']=[{'id':x.public_id,'title':x.content.get('title',''),'code':x.content.get('code',''),
                            'issuer':x.content.get('issuer',''),'status':x.status} for x in siblings]
            c['sibling_total']=s.scalar(select(func.count()).select_from(CatalogTarget).where(
                CatalogTarget.opportunity_id == opp.opportunity_id,
                CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']),
                CatalogTarget.public_id != public_id)) or 0
            return c

    def target_history(self, public_id, limit=20):
        if not 1 <= limit <= 100:
            raise Problem('分页参数不正确')
        with self.db.tx(False) as s:
            rows=list(s.scalars(
                select(CatalogTarget)
                .where(CatalogTarget.public_id==public_id)
                .order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc())
                .limit(limit)
            ))
            if not rows:
                raise Problem('具体机会不存在',404)
            versions=[]
            for row in rows:
                content=row.content if isinstance(row.content,dict) else {}
                currentness=content.get('currentness') if isinstance(content.get('currentness'),dict) else None
                versions.append({
                    'catalog_target_id':row.id,
                    'publication_id':row.publication_id,
                    'revision_id':row.revision_id,
                    'status':row.status,
                    'created_at':row.created_at.isoformat(),
                    'title':content.get('title',''),
                    'code':content.get('code',''),
                    'deadline':content.get('deadline'),
                    'deadline_precision':content.get('deadline_precision'),
                    'currentness':copy.deepcopy(currentness),
                })
            return {'target_public_id':public_id,'current_status':rows[0].status,'versions':versions}

    def compare_target_versions(self, public_id, from_id, to_id):
        with self.db.tx(False) as s:
            before=s.get(CatalogTarget,from_id);after=s.get(CatalogTarget,to_id)
            if not before or not after or before.public_id!=public_id or after.public_id!=public_id:
                raise Problem('版本不存在或不属于此具体机会',404)
            diff=diff_target_content(before.content or {},after.content or {})
            # The public comparison surface is intentionally small and stable;
            # raw structural/evidence detail remains available in the review data.
            changes={}
            for key,pair in diff.get('scalar',{}).items():
                changes[key]=pair
            if diff.get('fields'):
                changes['fields']=diff['fields']
            return {
                'target_public_id':public_id,
                'from_id':from_id,
                'to_id':to_id,
                'changes':changes,
                'affected_fields':diff.get('affected_fields',[]),
            }

    def announcement(self, public_id):
        with self.db.tx(False) as s:
            opp=s.scalar(select(Opportunity).where(Opportunity.public_id==public_id))
            if not opp:raise Problem('公告不存在',404)
            p=s.scalar(select(Publication).where(Publication.opportunity_id==opp.opportunity_id,Publication.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(Publication.created_at.desc()))
            if not p:raise Problem('公告已撤回或暂不可查看',410,'WITHDRAWN')
            return self._public(s,p,opp)
