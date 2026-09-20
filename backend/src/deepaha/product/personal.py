import copy
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .models import (
    Profile, ProfileRevision, PreparationItem, Action, Feedback, Notice, Opportunity, Publication,
    CatalogTarget, TargetAction, TargetFeedback, TargetNotice, TargetActionEvent, FeedbackCandidate, now,
)
from .adapter import text
from .errors import Problem

ACTION_STATES={'SAVED','PREPARING','APPLIED','WAITING','COMPLETED','DISMISSED'}
PROFILE_KEYS={'display_name','education','degree','major','major_code','graduation_year','student_status','birth_date','hukou_region','nationality','political_status','work_experience_years','certificates','professional_title','language_certificates','team_size','cities','interests','goals','skills','notification_enabled','notification_deadline_enabled','notification_change_enabled','notification_weekly_enabled','deadline_reminder_days','opportunity_types','career_directions','constraints','region_preference_mode','personalization_enabled'}

class PersonalMixin:
    def _profile(self,s,account_id):
        p=s.get(Profile,account_id)
        return copy.deepcopy(p.data) if p else {}
    def get_profile(self,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor);return self._profile(s,a.id)
    def _validate_profile(self,data):
        if not isinstance(data,dict) or set(data)-PROFILE_KEYS:raise Problem('画像字段不正确')
        cleaned={}
        for k,v in data.items():
            if k in ('notification_enabled','notification_deadline_enabled','notification_change_enabled','notification_weekly_enabled','personalization_enabled'):
                if not isinstance(v,bool):raise Problem('开关设置不正确')
                cleaned[k]=v
            elif k in ('cities','interests','goals','skills','career_directions','constraints','certificates','language_certificates'):
                if not isinstance(v,list) or len(v)>30 or any(not isinstance(x,str) or len(x)>100 for x in v):raise Problem('偏好项目过多或过长')
                cleaned[k]=list(dict.fromkeys(x.strip() for x in v if x.strip()))
            elif k=='deadline_reminder_days':
                if not isinstance(v,list) or len(v)>5 or any(not isinstance(x,int) or not 1<=x<=30 for x in v):raise Problem('提醒提前天数不正确')
                cleaned[k]=sorted(set(v),reverse=True)
            elif k=='opportunity_types':
                from .value import PERSONALIZABLE_TYPES
                if not isinstance(v,list) or len(v)>20 or any(x not in PERSONALIZABLE_TYPES for x in v):raise Problem('机会类型偏好不正确')
                cleaned[k]=list(dict.fromkeys(v))
            elif k=='region_preference_mode':
                if v not in ('FLEXIBLE','PREFERRED','STRICT'):raise Problem('地区偏好模式不正确')
                cleaned[k]=v
            elif k=='graduation_year':
                if v not in ('',None) and (not isinstance(v,int) or not 1950<=v<=2100):raise Problem('毕业年份不正确')
                cleaned[k]=v
            elif k=='work_experience_years':
                if v in ('',None):cleaned[k]=None
                elif not isinstance(v,(int,float)) or not 0<=float(v)<=80:raise Problem('工作经历年限不正确')
                else:cleaned[k]=float(v)
            elif k=='team_size':
                if v in ('',None):cleaned[k]=None
                elif not isinstance(v,int) or not 1<=v<=100:raise Problem('团队人数不正确')
                else:cleaned[k]=v
            elif k=='degree':
                if v not in ('','无','学士','硕士','博士'):raise Problem('学位信息不正确')
                cleaned[k]=v
            elif k=='student_status':
                if v not in ('','应届毕业生','在校生','非应届','往届','已就业','其他'):raise Problem('在读/毕业状态不正确')
                cleaned[k]=v
            elif k=='political_status':
                if v not in ('','中共党员','中共预备党员','共青团员','群众','其他'):raise Problem('政治面貌不正确')
                cleaned[k]=v
            elif k=='birth_date':
                if v in ('',None):cleaned[k]=''
                elif not isinstance(v,str):raise Problem('出生日期不正确')
                else:
                    try: birth=date.fromisoformat(v)
                    except ValueError: raise Problem('出生日期不正确')
                    if not date(1900,1,1)<=birth<=date.today():raise Problem('出生日期不正确')
                    cleaned[k]=birth.isoformat()
            elif k=='major_code':
                import re
                if v in ('',None):cleaned[k]=''
                elif not isinstance(v,str) or not re.fullmatch(r'\d{2,8}',v.strip()):raise Problem('专业代码不正确')
                else:cleaned[k]=v.strip()
            else:
                if not isinstance(v,str) or len(v)>300:raise Problem('画像内容过长')
                cleaned[k]=v.strip()
        return cleaned

    def _profile_version(self,s,account_id):
        row=s.get(ProfileRevision,account_id)
        return row.version if row else 0

    def _bump_profile_version(self,s,account_id):
        row=s.get(ProfileRevision,account_id)
        if not row:row=ProfileRevision(account_id=account_id,version=0);s.add(row)
        row.version+=1
        return row.version

    def _save_profile(self,s,a,cleaned,actor):
        p=s.get(Profile,a.id)
        if p:p.data=cleaned;p.updated_at=now()
        else:s.add(Profile(account_id=a.id,data=cleaned))
        profile=self._profile(s,a.id)
        if profile.get('notification_enabled') is False:
            for cls in (Notice,TargetNotice):
                for n in s.scalars(select(cls).where(cls.account_id==a.id,cls.state!='CANCELLED')):n.state='CANCELLED'
        else:
            if profile.get('notification_deadline_enabled') is False:self._cancel_notice_kind(s,a.id,'DEADLINE')
            if profile.get('notification_change_enabled') is False:self._cancel_notice_kind(s,a.id,'CHANGE')
            if profile.get('notification_weekly_enabled') is False:self._cancel_notice_kind(s,a.id,'WEEKLY')
            self._sync_all_action_deadlines(s,a.id,profile)
        self._audit(s,actor,'UPDATE_PROFILE',a.id,'更新个人偏好与通知开关；未发送外部模型')
        return self._bump_profile_version(s,a.id)

    def set_profile(self,data,*,actor):
        # Legacy PUT deliberately retains full-replacement semantics.
        cleaned=self._validate_profile(data)
        with self.db.tx() as s:
            a=self._account(s,actor);self._save_profile(s,a,cleaned,actor)
        return cleaned

    def profile_state(self,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            return {'profile':self._profile(s,a.id),'version':self._profile_version(s,a.id)}

    def patch_profile(self,changes,expected_version,*,actor):
        if type(expected_version) is not int or expected_version<0:raise Problem('资料版本不正确')
        cleaned_changes=self._validate_profile(changes)
        with self.db.tx() as s:
            a=self._account(s,actor)
            if self._profile_version(s,a.id)!=expected_version:
                raise Problem('资料已在别处更新；请先查看最新资料，再确认合并',409,'PROFILE_CHANGED')
            merged={**self._profile(s,a.id),**cleaned_changes}
            if not cleaned_changes:return {'profile':merged,'version':expected_version}
            version=self._save_profile(s,a,merged,actor)
            return {'profile':merged,'version':version}

    def _target_row(self,s,public_id):
        row=self._current_target(s,public_id)
        if not row:raise Problem('机会不存在或已撤回',404)
        return row

    def set_action(self,public_id,status,*,actor,note=''):
        if status not in ACTION_STATES:raise Problem('行动状态不正确')
        if not isinstance(note,str) or len(note)>2000:raise Problem('行动备注过长')
        with self.db.tx() as s:
            a=self._account(s,actor);target=self._target_row(s,public_id)
            self._set_action_row(s,a,target,status,note,'STATUS')
            return {'id':target.public_id,'status':status,'note':note}

    def remove_action(self,public_id,*,actor):
        with self.db.tx() as s:
            a=self._account(s,actor);target=self._target_row(s,public_id)
            row=s.scalar(select(TargetAction).where(TargetAction.account_id==a.id,TargetAction.target_public_id==public_id))
            if row:
                self._record_action_event(s,a.id,target,row.status,'DISMISSED',row.note,'REMOVE')
                s.delete(row)
            for n in s.scalars(select(TargetNotice).where(TargetNotice.account_id==a.id,TargetNotice.target_public_id==public_id,TargetNotice.kind=='DEADLINE')):n.state='CANCELLED'
        return {'removed':True}

    def my_actions(self,*,actor,offset=0,limit=50,_envelope=False,status=''):
        with self.db.tx(False) as s:
            a=self._account(s,actor);result=[]
            target_actions=list(s.scalars(select(TargetAction).where(TargetAction.account_id==a.id).order_by(TargetAction.updated_at.desc(),TargetAction.id)))
            for ac in target_actions:
                target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==ac.target_public_id,CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(CatalogTarget.created_at.desc()))
                if target:
                    opp=s.get(Opportunity,target.opportunity_id);c=self._target(target,opp)
                else:
                    c={'id':ac.target_public_id,'title':'已撤回的具体机会','status':'WITHDRAWN','deadline':None,'type':'YOUTH_DEVELOPMENT_PROGRAM','notes':['该具体机会已撤回。']}
                result.append({'opportunity':c,'status':ac.status,'note':ac.note,'updated_at':ac.updated_at.isoformat(),'legacy_scope':False})
            # Preserve old rc2 root-level actions. Never guess a child target for a multi-unit root.
            for ac,o in s.execute(select(Action,Opportunity).join(Opportunity,Action.opportunity_id==Opportunity.opportunity_id).where(Action.account_id==a.id).order_by(Action.updated_at.desc(),Action.id)):
                p=s.scalar(select(Publication).where(Publication.opportunity_id==o.opportunity_id,Publication.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(Publication.created_at.desc()))
                c=self._public(s,p,o) if p else {'id':o.public_id,'title':o.canonical_title,'status':'WITHDRAWN','deadline':None,'type':o.type,'notes':['该机会已撤回。']}
                c['notes']=list(dict.fromkeys(c.get('notes',[])+['这是旧版公告级行动记录，未自动映射到任何具体岗位或赛道。']))
                result.append({'opportunity':c,'status':ac.status,'note':ac.note,'updated_at':ac.updated_at.isoformat(),'legacy_scope':True})
            result.sort(key=lambda x:x['updated_at'],reverse=True)
            if _envelope:
                from collections import Counter
                counts=dict(Counter(x['status'] for x in result))
                if status:result=[x for x in result if x['status']==status]
                return {'items':result[offset:offset+min(limit,50)],'total':len(result),'counts':counts,'offset':offset,'limit':limit}
            return result[offset:offset+min(limit,50)]

    def feedback(self,public_id,data,*,actor):
        keys={'previously_known','useful','action_reason','outcome','comment'}
        if not isinstance(data,dict) or set(data)-keys:raise Problem('反馈字段不正确')
        if data.get('previously_known') not in (None,True,False) or data.get('useful') not in (None,True,False):raise Problem('反馈选项不正确')
        if data.get('outcome') not in (None,'','APPLIED','INTERVIEW','ACCEPTED','REJECTED','NO_RESULT','ABANDONED'):raise Problem('结果选项不正确')
        payload={k:(text(v,2000) if isinstance(v,str) else v) for k,v in data.items()}
        from .action_loop import OUTCOME_TO_ACTION
        with self.db.tx() as s:
            a=self._account(s,actor);target=self._target_row(s,public_id)
            fb=TargetFeedback(account_id=a.id,target_public_id=public_id,opportunity_id=target.opportunity_id,data=payload)
            s.add(fb);s.flush()
            action=s.scalar(select(TargetAction).where(TargetAction.account_id==a.id,TargetAction.target_public_id==public_id))
            outcome=payload.get('outcome')
            desired=OUTCOME_TO_ACTION.get(outcome)
            if desired:
                if action is None or action.status!='COMPLETED':
                    action=self._set_action_row(s,a,target,desired,action.note if action else '',event_type='OUTCOME')
            candidate=FeedbackCandidate(feedback_id=fb.id,target_public_id=public_id,opportunity_id=target.opportunity_id,
                candidate_kind='OUTCOME' if outcome else 'SIGNAL',state='CANDIDATE',
                data=self._feedback_candidate_payload(target,action,payload))
            s.add(candidate)
        return {'saved':True,'evaluation_candidate':'CANDIDATE'}

    def recommendations(self,*,actor,limit=20):
        from .eligibility import evaluate
        from .value import assess,public_assessment,retrieval_score,diversify,inferred_types
        limit=min(max(int(limit),1),50);candidate_limit=120
        with self.db.tx(False) as s:
            a=self._account(s,actor);profile=self._profile(s,a.id)
            if profile.get('personalization_enabled',True) is False:
                return {'items':[],'featured':[],'personalization_enabled':False,'basis':'LOCAL_VALUE_PRIORITY_V1','llm_used':False,'candidate_limit':candidate_limit,'candidate_count':0,'evaluated_count':0,'excluded_ineligible':0,'inferred_opportunity_types':[]}
            stmt=(select(CatalogTarget,Opportunity).join(Opportunity,CatalogTarget.opportunity_id==Opportunity.opportunity_id)
                  .where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
                  .order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc()))
            selected_types=list(dict.fromkeys(profile.get('opportunity_types') or []))
            inferred=list(dict.fromkeys(inferred_types(profile))) if not selected_types else []
            # Explicit type choices are a hard retrieval preference.  Inferred types
            # are only one channel: retain a small recent exploration channel so a
            # progressive profile never becomes a closed filter bubble.
            if selected_types:
                rows=list(s.execute(stmt.where(CatalogTarget.content['type'].as_string().in_(selected_types)).limit(240)))
            elif inferred:
                primary=list(s.execute(stmt.where(CatalogTarget.content['type'].as_string().in_(inferred)).limit(180)))
                exploratory=list(s.execute(stmt.limit(60)))
                seen=set();rows=[]
                for pair in primary+exploratory:
                    target=pair[0]
                    if target.id in seen:continue
                    seen.add(target.id);rows.append(pair)
            else:
                rows=list(s.execute(stmt.limit(240)))
            # First-stage retrieval is deliberately bounded and cheap.  It does not
            # invoke SG4 evidence evaluation or any external model.
            actions={x.target_public_id:x.status for x in s.scalars(select(TargetAction).where(TargetAction.account_id==a.id))}
            negatives=set()
            for fb in s.scalars(select(TargetFeedback).where(TargetFeedback.account_id==a.id)):
                data=fb.data if isinstance(fb.data,dict) else {}
                if data.get('useful') is False:negatives.add(fb.target_public_id)
            ranked=[]
            for target,opp in rows:
                if actions.get(target.public_id) in {'DISMISSED','COMPLETED'}:continue
                content=self._target(target,opp)
                mode=profile.get('region_preference_mode','FLEXIBLE')
                if mode=='STRICT' and profile.get('cities') and content.get('region'):
                    from .value import _region_match
                    if not _region_match(content.get('region',''),profile.get('cities')):continue
                ranked.append((retrieval_score(content,profile),target.created_at,target.id,target,opp,content))
            ranked.sort(key=lambda x:(-x[0],-x[1].timestamp(),x[2]))
            pool=ranked[:candidate_limit]
        items=[];excluded=0
        for _,_,_,target,opp,content in pool:
            eligibility=evaluate(self,target,opp,profile)
            if eligibility.get('status')=='INELIGIBLE':excluded+=1;continue
            value=assess(content,profile,eligibility,action_status=actions.get(target.public_id),negative_feedback=target.public_id in negatives)
            if value.get('priority_band')=='NOT_RECOMMENDED':continue
            merged=dict(content);merged.update(public_assessment(value));merged['_score']=value['_score']
            items.append(merged)
        items.sort(key=lambda x:(-x['_score'],x.get('deadline') or '9999-99-99',x.get('id') or ''))
        public=[]
        for item in items[:limit]:
            item=dict(item);item.pop('_score',None);item['reasons']=item.get('why_for_you',[])
            public.append(item)
        headline=[x for x in public if x.get('qualification_gate')!='HOLD_FOR_CONFIRMATION']
        featured=diversify(headline,min(3,len(headline)))
        result={'items':public,'featured':featured,'personalization_enabled':True,'basis':'LOCAL_VALUE_PRIORITY_V1','llm_used':False,
                'candidate_limit':candidate_limit,'candidate_count':len(pool),'evaluated_count':len(pool),'excluded_ineligible':excluded,
                'inferred_opportunity_types':inferred}
        # SG7 exposure logging is explicit-consent-only and records only target/version IDs.
        # It never sends the profile to WMA and never changes recommendation output.
        self.lab_record_exposures(actor=actor,items=public)
        return result

    def value(self,public_id,*,actor):
        from .eligibility import evaluate
        from .value import assess,public_assessment
        with self.db.tx(False) as s:
            a=self._account(s,actor);profile=self._profile(s,a.id)
            if profile.get('personalization_enabled',True) is False:
                return {'target_id':public_id,'personalization_enabled':False,'basis':'LOCAL_VALUE_PRIORITY_V1','llm_used':False,
                        'why_for_you':[],'why_now':'个性化已关闭。','risks':['你已关闭个性化机会排序。']}
            target=self._target_row(s,public_id);opp=s.get(Opportunity,target.opportunity_id)
            action=s.scalar(select(TargetAction).where(TargetAction.account_id==a.id,TargetAction.target_public_id==public_id))
            negative=any((fb.data or {}).get('useful') is False for fb in s.scalars(select(TargetFeedback).where(TargetFeedback.account_id==a.id,TargetFeedback.target_public_id==public_id)))
            content=self._target(target,opp)
        eligibility=evaluate(self,target,opp,profile)
        value=assess(content,profile,eligibility,action_status=action.status if action else None,negative_feedback=negative)
        out=public_assessment(value);out['target_id']=public_id;return out

    def fit(self,public_id,*,actor):
        from .eligibility import evaluate
        profile=self.get_profile(actor=actor)
        with self.db.tx(False) as s:
            target=self._current_target(s,public_id)
            if not target:raise Problem('机会不存在或已撤回',404)
            opp=s.get(Opportunity,target.opportunity_id)
        result=evaluate(self,target,opp,profile)
        result['target_id']=public_id
        return result

    def set_reminder(self,public_id,*,actor,days_before=1):
        if not 1<=days_before<=30:raise Problem('提前天数应为1至30天')
        with self.db.tx() as s:
            a=self._account(s,actor);target=self._target_row(s,public_id)
            profile=self._profile(s,a.id)
            if profile.get('notification_enabled') is False or profile.get('notification_deadline_enabled') is False:raise Problem('你已关闭截止提醒',409)
            day=target.content.get('deadline') if target.status=='CURRENT' else None
            if not day:raise Problem('报名时间尚不确定，不能设置截止提醒',409,'UNCERTAIN_DATE')
            target_day=date.fromisoformat(day)-timedelta(days=days_before)
            due=datetime.combine(target_day,time(8),ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
            if date.fromisoformat(day)<datetime.now(ZoneInfo('Asia/Shanghai')).date():raise Problem('报名截止日期已过',409)
            dedupe=f'target-deadline:{target.id}:{days_before}'
            n=s.scalar(select(TargetNotice).where(TargetNotice.account_id==a.id,TargetNotice.dedupe_key==dedupe))
            if n:n.state='UNREAD';n.due_at=due
            else:s.add(TargetNotice(account_id=a.id,target_public_id=public_id,opportunity_id=target.opportunity_id,catalog_target_id=target.id,title='你关注的具体机会即将截止',body=f'{target.content["title"]}；材料标注报名截止日期为{day}。',kind='DEADLINE',dedupe_key=dedupe,due_at=due))
        return {'scheduled':True,'date':day,'days_before':days_before,'channel':'IN_APP'}

    def notifications(self,*,actor,offset=0,limit=50,unread=False,_envelope=False):
        with self.db.tx(False) as s:
            a=self._account(s,actor);out=[]
            for n in s.scalars(select(TargetNotice).where(TargetNotice.account_id==a.id,TargetNotice.state!='CANCELLED',TargetNotice.due_at<=now())):
                out.append({'id':n.id,'title':n.title,'body':n.body,'kind':n.kind,'state':n.state,'opportunity_id':n.target_public_id,'created_at':n.created_at.isoformat()})
            for n in s.scalars(select(Notice).where(Notice.account_id==a.id,Notice.state!='CANCELLED',Notice.due_at<=now())):
                o=s.get(Opportunity,n.opportunity_id) if n.opportunity_id else None
                out.append({'id':n.id,'title':n.title,'body':n.body,'kind':n.kind,'state':n.state,'opportunity_id':o.public_id if o else None,'created_at':n.created_at.isoformat()})
            unread_count=sum(x['state']!='READ' for x in out)
            if unread:out=[x for x in out if x['state']!='READ']
            out.sort(key=lambda x:(x['created_at'],x['id']),reverse=True)
            if _envelope:return {'items':out[offset:offset+min(limit,50)],'total':len(out),'unread_count':unread_count,'offset':offset,'limit':limit}
            return out[offset:offset+min(limit,50)]

    def mark_read(self,id,*,actor):
        with self.db.tx() as s:
            a=self._account(s,actor)
            n=s.get(TargetNotice,id)
            if n is None:n=s.get(Notice,id)
            if not n or n.account_id!=a.id:raise Problem('通知不存在',404)
            if n.state!='CANCELLED':n.state='READ'
        return {'read':True}

    def calendar(self,public_id):
        # Calendar identity belongs to the actionable target, even when a root-only
        # opportunity uses its historical opp_* public id as the singleton card id.
        with self.db.tx(False) as s:
            target=self._current_target(s,public_id)
            if not target:raise Problem('具体机会不存在或已撤回',404)
            target_id=target.id
        c=self.detail(public_id)
        if not c['deadline']:raise Problem('报名时间尚不确定，不能导出日历',409)
        d=date.fromisoformat(c['deadline'])
        def esc(v):return v.replace('\\','\\\\').replace('\n','\\n').replace(',','\\,').replace(';','\\;').replace('\r','')
        lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//DeepAha//Opportunity//ZH','CALSCALE:GREGORIAN','BEGIN:VEVENT',
          'UID:'+target_id+'@deepaha','DTSTAMP:'+now().strftime('%Y%m%dT%H%M%SZ'),
          'DTSTART;VALUE=DATE:'+d.strftime('%Y%m%d'),'DTEND;VALUE=DATE:'+(d+timedelta(days=1)).strftime('%Y%m%d'),
          'SUMMARY:'+esc(c['title']+' · 报名截止日期'),
          'DESCRIPTION:'+esc('此日历记录材料中的日期，不代表已确认当日的具体截止时刻。请查看最新官方公告。'),
          'URL:'+c['official_url'],'END:VEVENT','END:VCALENDAR']
        folded=[]
        for line in lines:
            part='';size=0
            for ch in line:
                n=len(ch.encode())
                if size+n>74:folded.append(part);part=' ';size=1
                part+=ch;size+=n
            folded.append(part)
        return ('\r\n'.join(folded)+'\r\n').encode()

    def export_personal(self,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            feed=[{'opportunity_id':f.target_public_id,'data':f.data,'created_at':f.created_at.isoformat()} for f in s.scalars(select(TargetFeedback).where(TargetFeedback.account_id==a.id))]
            for f in s.scalars(select(Feedback).where(Feedback.account_id==a.id)):
                o=s.get(Opportunity,f.opportunity_id);feed.append({'opportunity_id':o.public_id if o else None,'data':f.data,'created_at':f.created_at.isoformat(),'legacy_scope':True})
        actions=[]
        while True:
            page=self.my_actions(actor=actor,offset=len(actions),limit=50);actions.extend(page)
            if len(page)<50:break
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            current={x.target_public_id:x for x in s.scalars(select(TargetAction).where(TargetAction.account_id==a.id))}
            events=list(s.scalars(select(TargetActionEvent).where(TargetActionEvent.account_id==a.id).order_by(
                TargetActionEvent.target_public_id,TargetActionEvent.created_at,TargetActionEvent.id)))
        grouped={}
        for event in events:
            grouped.setdefault(event.target_public_id,[]).append({
                'id':event.id,'from_status':event.from_status,'to_status':event.to_status,'note':event.note,
                'event_type':event.event_type,'created_at':event.created_at.isoformat(),
            })
        histories=[]
        for target_id,event_rows in grouped.items():
            action=current.get(target_id)
            histories.append({'target_id':target_id,'current_status':action.status if action else None,
                              'note':action.note if action else '', 'events':event_rows})
        from .models import LabEnrollment, LabExposure
        with self.db.tx(False) as s:
            a=self._account(s,actor);enrollment=s.get(LabEnrollment,a.id)
            exposures=[{'target_id':x.target_public_id,'publication_id':x.publication_id,'first_seen_at':x.first_seen_at.isoformat()}
                       for x in s.scalars(select(LabExposure).where(LabExposure.account_id==a.id).order_by(LabExposure.first_seen_at))]
            lab={'status':enrollment.status if enrollment else 'NOT_JOINED','cohort':enrollment.cohort if enrollment else None,
                 'consent_version':enrollment.consent_version if enrollment else None,'joined_at':enrollment.joined_at.isoformat() if enrollment else None,
                 'withdrawn_at':enrollment.withdrawn_at.isoformat() if enrollment and enrollment.withdrawn_at else None,'exposures':exposures}
        return {'profile':self.get_profile(actor=actor),'preparation_items':self.preparation_items(actor=actor)['items'],'actions':actions,'action_history':histories,'feedback':feed,'opportunity_lab':lab}

    def erase_personal(self,*,actor):
        with self.db.tx() as s:
            a=self._account(s,actor)
            feedback_ids=list(s.scalars(select(TargetFeedback.id).where(TargetFeedback.account_id==a.id)))
            if feedback_ids:
                for row in s.scalars(select(FeedbackCandidate).where(FeedbackCandidate.feedback_id.in_(feedback_ids))):s.delete(row)
            from .models import LabEnrollment, LabExposure
            for cls in (PreparationItem,LabExposure,TargetActionEvent,Profile,TargetAction,TargetFeedback,TargetNotice,Action,Feedback,Notice):
                for row in s.scalars(select(cls).where(cls.account_id==a.id)):s.delete(row)
            enrollment=s.get(LabEnrollment,a.id)
            if enrollment:s.delete(enrollment)
            self._bump_profile_version(s,a.id)
            self._audit(s,actor,'ERASE_PERSONAL',a.id,'已删除画像、行动时间线、反馈、派生评估候选、SG7共创记录和个人通知')
        return {'erased':True}
