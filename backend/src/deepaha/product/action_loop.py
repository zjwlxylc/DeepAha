"""SG6 user action loop: durable transitions, safe reminders, weekly digest and offline feedback candidates."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import func, select

from .errors import Problem
from .models import (
    Account, CatalogTarget, FeedbackCandidate, Notice, Opportunity, Profile,
    TargetAction, TargetActionEvent, TargetFeedback, TargetNotice, now,
)

ACTIVE_ACTION_STATES={'SAVED','PREPARING'}
TERMINAL_ACTION_STATES={'COMPLETED','DISMISSED'}
OUTCOME_TO_ACTION={
    'APPLIED':'APPLIED', 'INTERVIEW':'WAITING', 'NO_RESULT':'WAITING',
    'ACCEPTED':'COMPLETED', 'REJECTED':'COMPLETED', 'ABANDONED':'COMPLETED',
}
DEFAULT_REMINDER_DAYS=[7,1]


def notification_preferences(profile: dict) -> dict:
    return {
        'master': profile.get('notification_enabled', True) is not False,
        'deadline': profile.get('notification_deadline_enabled', True) is not False,
        'change': profile.get('notification_change_enabled', True) is not False,
        'weekly': profile.get('notification_weekly_enabled', True) is not False,
        'days': list(profile.get('deadline_reminder_days') or DEFAULT_REMINDER_DAYS),
    }


class ActionLoopMixin:
    def _record_action_event(self,s,account_id,target,from_status,to_status,note='',event_type='STATUS',created_at=None):
        s.add(TargetActionEvent(
            account_id=account_id,target_public_id=target.public_id,opportunity_id=target.opportunity_id,
            from_status=from_status,to_status=to_status,note=note or '',event_type=event_type,
            created_at=created_at or now(),
        ))

    def _set_action_row(self,s,account,target,status,note='',event_type='STATUS'):
        row=s.scalar(select(TargetAction).where(
            TargetAction.account_id==account.id,TargetAction.target_public_id==target.public_id))
        old=row.status if row else None
        old_note=row.note if row else ''
        if row:
            row.status=status;row.note=note;row.updated_at=now()
        else:
            row=TargetAction(account_id=account.id,target_public_id=target.public_id,
                opportunity_id=target.opportunity_id,status=status,note=note)
            s.add(row);s.flush()
        if old!=status or old_note!=note:
            self._record_action_event(s,account.id,target,old,status,note,event_type)
        self._sync_deadline_notices(s,account.id,target,status,self._profile(s,account.id))
        return row

    def action_history(self,public_id,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            action=s.scalar(select(TargetAction).where(
                TargetAction.account_id==a.id,TargetAction.target_public_id==public_id))
            if not action:raise Problem('这项机会还没有行动记录',404)
            rows=list(s.scalars(select(TargetActionEvent).where(
                TargetActionEvent.account_id==a.id,TargetActionEvent.target_public_id==public_id)
                .order_by(TargetActionEvent.created_at,TargetActionEvent.id)))
            return {'target_id':public_id,'current_status':action.status,'note':action.note,
                    'events':[{'id':x.id,'from_status':x.from_status,'to_status':x.to_status,
                               'note':x.note,'event_type':x.event_type,'created_at':x.created_at.isoformat()} for x in rows]}

    def _cancel_notice_kind(self,s,account_id,kind):
        for cls in (TargetNotice,Notice):
            for n in s.scalars(select(cls).where(cls.account_id==account_id,cls.kind==kind,cls.state!='CANCELLED')):
                n.state='CANCELLED'

    def _sync_deadline_notices(self,s,account_id,target,status,profile):
        # Always invalidate previous schedule for this target before deciding whether a new one is safe.
        for n in s.scalars(select(TargetNotice).where(
            TargetNotice.account_id==account_id,TargetNotice.target_public_id==target.public_id,
            TargetNotice.kind=='DEADLINE',TargetNotice.state!='CANCELLED')):
            n.state='CANCELLED'
        prefs=notification_preferences(profile)
        if not prefs['master'] or not prefs['deadline'] or status not in ACTIVE_ACTION_STATES:return
        if target.status!='CURRENT':return
        day=(target.content or {}).get('deadline')
        readiness=(target.content or {}).get('time_readiness') or {}
        if not day or readiness.get('state') not in (None,'READY'):return
        try:deadline=date.fromisoformat(day)
        except (TypeError,ValueError):return
        today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
        if deadline<today:return
        for days in sorted(set(int(x) for x in prefs['days'] if isinstance(x,int) and 1<=x<=30),reverse=True):
            trigger=deadline-timedelta(days=days)
            if trigger<today:continue
            due=datetime.combine(trigger,time(8),ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
            dedupe=f'target-deadline:{target.id}:{days}'
            existing=s.scalar(select(TargetNotice).where(TargetNotice.account_id==account_id,TargetNotice.dedupe_key==dedupe))
            title=f'你关注的具体机会将在{days}天后截止'
            body=f'{target.content.get("title","具体机会")}；当前安全报名截止为{day}。请在行动页检查准备进度。'
            if existing:
                existing.state='UNREAD';existing.due_at=due;existing.title=title;existing.body=body
            else:
                s.add(TargetNotice(account_id=account_id,target_public_id=target.public_id,
                    opportunity_id=target.opportunity_id,catalog_target_id=target.id,title=title,body=body,
                    kind='DEADLINE',dedupe_key=dedupe,due_at=due))

    def _reschedule_target_followers(self,s,target):
        for action in s.scalars(select(TargetAction).where(TargetAction.target_public_id==target.public_id)):
            self._sync_deadline_notices(s,action.account_id,target,action.status,self._profile(s,action.account_id))

    def _sync_all_action_deadlines(self,s,account_id,profile):
        actions=list(s.scalars(select(TargetAction).where(TargetAction.account_id==account_id)))
        for action in actions:
            target=s.scalar(select(CatalogTarget).where(
                CatalogTarget.public_id==action.target_public_id,CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
                .order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc()))
            if target:self._sync_deadline_notices(s,account_id,target,action.status,profile)

    def _feedback_candidate_payload(self,target,action,payload):
        return {
            'opportunity_type':(target.content or {}).get('type'),
            'previously_known':payload.get('previously_known'),
            'useful':payload.get('useful'),
            'action_reason':payload.get('action_reason'),
            'outcome':payload.get('outcome'),
            'action_status':action.status if action else None,
            'comment_present':bool(payload.get('comment')),
            'source':'USER_FEEDBACK',
        }

    def feedback_candidates(self,*,actor,offset=0,limit=50):
        limit=min(max(int(limit),1),100);offset=max(int(offset),0)
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            total=s.scalar(select(func.count()).select_from(FeedbackCandidate)) or 0
            rows=list(s.scalars(select(FeedbackCandidate).order_by(
                FeedbackCandidate.created_at.desc(),FeedbackCandidate.id.desc()).offset(offset).limit(limit)))
            return {'total':total,'items':[{
                'id':x.id,'target_id':x.target_public_id,'kind':x.candidate_kind,'state':x.state,
                'opportunity_type':(x.data or {}).get('opportunity_type'),
                'previously_known':(x.data or {}).get('previously_known'),'useful':(x.data or {}).get('useful'),
                'action_reason':(x.data or {}).get('action_reason'),'outcome':(x.data or {}).get('outcome'),
                'action_status':(x.data or {}).get('action_status'),'created_at':x.created_at.isoformat(),
            } for x in rows]}

    def weekly_digest(self,*,actor,at=None):
        at=at or now();local=at.astimezone(ZoneInfo('Asia/Shanghai'))
        year,week,_=local.isocalendar();period=f'{year}-W{week:02d}'
        actions=self.my_actions(actor=actor,_all=True)
        counts=Counter(x['status'] for x in actions)
        due=[]
        today=local.date()
        action_ids={x['opportunity']['id'] for x in actions}
        for x in actions:
            raw=x['opportunity'].get('deadline')
            if not raw:continue
            try:d=date.fromisoformat(raw)
            except ValueError:continue
            if today<=d<=today+timedelta(days=7):
                due.append({'id':x['opportunity']['id'],'title':x['opportunity']['title'],'deadline':raw,'status':x['status']})
        rec=self.recommendations(actor=actor,limit=8)
        fresh=[]
        for x in rec.get('items',[]):
            if x['id'] in action_ids:continue
            fresh.append({'id':x['id'],'title':x['title'],'priority_band':x.get('priority_band'),'why_now':x.get('why_now')})
            if len(fresh)>=3:break
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            changes=[]
            for n in s.scalars(select(TargetNotice).where(
                TargetNotice.account_id==a.id,TargetNotice.kind=='CHANGE',TargetNotice.state!='CANCELLED')
                .order_by(TargetNotice.created_at.desc()).limit(5)):
                changes.append({'id':n.id,'target_id':n.target_public_id,'title':n.title,'body':n.body,'state':n.state})
        return {'period_key':period,'generated_at':at.isoformat(),
                'action_summary':{k:counts.get(k,0) for k in ['SAVED','PREPARING','APPLIED','WAITING','COMPLETED','DISMISSED']},
                'due_soon':due,'changes':changes,'new_opportunities':fresh}

    def create_weekly_digest_notice(self,*,actor,at=None):
        at=at or now()
        profile=self.get_profile(actor=actor);prefs=notification_preferences(profile)
        if not prefs['master'] or not prefs['weekly']:return None
        local=at.astimezone(ZoneInfo('Asia/Shanghai'));year,week,_=local.isocalendar();period=f'{year}-W{week:02d}'
        dedupe='weekly:'+period
        with self.db.tx(False) as s:
            a=self._account(s,actor)
            existing=s.scalar(select(Notice).where(Notice.account_id==a.id,Notice.dedupe_key==dedupe))
            if existing:return {'id':existing.id,'period_key':period,'created':False}
        digest=self.weekly_digest(actor=actor,at=at)
        active=sum(digest['action_summary'][x] for x in ['SAVED','PREPARING','APPLIED','WAITING'])
        body=f'本周你有 {active} 项进行中的机会行动，{len(digest["due_soon"])} 项将在7天内截止，另有 {len(digest["new_opportunities"])} 项值得继续了解。'
        with self.db.tx() as s:
            a=self._account(s,actor)
            existing=s.scalar(select(Notice).where(Notice.account_id==a.id,Notice.dedupe_key==dedupe))
            if existing:return {'id':existing.id,'period_key':period,'created':False}
            n=Notice(account_id=a.id,opportunity_id=None,publication_id=None,title='你的本周机会摘要',body=body,
                     kind='WEEKLY',dedupe_key=dedupe,due_at=at)
            s.add(n);s.flush();return {'id':n.id,'period_key':period,'created':True}


def schedule_weekly_digests(product,at=None):
    at=at or now();users=[]
    with product.db.tx(False) as s:
        for account,profile in s.execute(select(Account,Profile).join(Profile,Profile.account_id==Account.id).where(Account.active.is_(True))):
            if 'user' not in (account.roles or []):continue
            prefs=notification_preferences(profile.data or {})
            if prefs['master'] and prefs['weekly']:users.append(account.username)
    created=0
    for username in users:
        result=product.create_weekly_digest_notice(actor=username,at=at)
        if result and result.get('created'):created+=1
    return created
