"""Evidence-backed time semantics for actionable opportunity targets.

This module never treats a date-looking string as a computable deadline by itself.
A milestone is computable only when its source field is current, semantically
recognized, deterministically parsed, and at least one evidence reference can be
re-located in immutable stored material through the SG4 EvidenceResolver.
"""
from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any

from sqlalchemy import select

from .eligibility import EvidenceResolver
from .models import CatalogTarget, Opportunity, Revision, Snapshot

ROLLING_TOKENS=('滚动受理','滚动申报','常年受理','全年受理','长期受理','长期有效','招满即止','随时申报','长期开放')
HISTORICAL_TOKENS=('原定','原截止','原时间','更正前','调整前','延期前','旧版')
CORRECTED_TOKENS=('更正后','调整后','延期后','最新','现行')
TIME_HINTS=('时间','日期','截止','报名','申请','受理','赛程','笔试','面试','缴费','准考证','公布','公示','registration','deadline','submit','exam','interview')


def _norm(value: object) -> str:
    return ' '.join(str(value or '').replace('\r',' ').replace('\n',' ').split())


def _field_key(scope: str, label: str, occurrence: int) -> str:
    return f'{scope}:{label}#{occurrence}'


def _is_time_field(label: str, value: str) -> bool:
    low=label.lower()
    if any(token in value for token in ROLLING_TOKENS):
        return True
    if any(token in low for token in ('registration_start','registration_deadline','application_start','application_deadline','deadline','exam_date','interview')):
        return True
    if any(token in label for token in ('时间','日期','截止','赛程','笔试','面试','缴费','准考证','公布','公示')):
        return True
    # 报名/申请/受理 can describe a method, quota or restriction.  Treat
    # them as time semantics only when the label or value actually carries
    # a temporal signal.
    if any(token in label for token in ('报名','申请','受理')):
        if any(token in label for token in ('开始','起始','截止','时间','日期','窗口','期限','开放')):
            return True
        if _DATE_RE.search(value) or _MONTH_RE.search(value):
            return True
    return False


def _classification(label: str, value: str) -> tuple[str,str,bool]:
    """Return (kind, mode, historical).

    mode is POINT, WINDOW or ROLLING.  APPLICATION_WINDOW is later expanded into
    APPLICATION_OPEN + APPLICATION_DEADLINE when both endpoints are deterministic.
    """
    low=label.lower().replace('-','_')
    historical=any(token in label for token in HISTORICAL_TOKENS)
    if any(token in value for token in ROLLING_TOKENS):
        return 'ROLLING_APPLICATION','ROLLING',historical
    if (('作品' in label or '材料' in label or '成果' in label or '提交' in label or 'submit' in low) and '截止' in label) or 'submission_deadline' in low:
        return 'SUBMISSION_DEADLINE','POINT',historical
    if '缴费' in label:
        return 'PAYMENT_WINDOW','WINDOW',historical
    if '准考证' in label:
        return 'ADMISSION_TICKET_WINDOW','WINDOW',historical
    if any(token in label for token in ('资格初审','资格审核','审核时间','审核日期')):
        return 'REVIEW_WINDOW','WINDOW',historical
    if '面试' in label or 'interview' in low:
        return 'INTERVIEW_DATE','POINT',historical
    if '笔试' in label or ('考试' in label and '报名' not in label) or 'exam_date' in low:
        return 'EXAM_DATE','POINT',historical
    if any(token in label for token in ('结果公布','结果公示','名单公布','公示时间')):
        return 'RESULT_DATE','POINT',historical
    if ('registration_deadline' in low or 'application_deadline' in low or
        (any(token in label for token in ('报名','申请','受理')) and '截止' in label)):
        return 'APPLICATION_DEADLINE','POINT',historical
    if ('registration_start' in low or 'application_start' in low or
        (any(token in label for token in ('报名','申请','受理')) and any(token in label for token in ('开始','起始','启动')))):
        return 'APPLICATION_OPEN','POINT',historical
    if ('registration' in low or 'application' in low or any(token in label for token in ('报名时间','申请时间','受理时间','申请窗口'))):
        return 'APPLICATION_WINDOW','WINDOW',historical
    return 'OTHER_TIME','WINDOW',historical


_DATE_RE=re.compile(
    r'(?:(?P<year>20\d{2})\s*[年\-/])?\s*'
    r'(?P<month>\d{1,2})\s*[月\-/]\s*'
    r'(?P<day>\d{1,2})\s*日?'
    r'(?:\s*(?P<hour>\d{1,2})(?:\s*[:：时]\s*(?P<minute>\d{1,2}))?\s*分?)?'
)
_MONTH_RE=re.compile(r'(?P<year>20\d{2})\s*年\s*(?P<month>\d{1,2})\s*月(?!\s*\d)')


def _points(value: str) -> list[dict]:
    out=[];year=None
    for m in _DATE_RE.finditer(value):
        raw_year=m.group('year')
        if raw_year:year=int(raw_year)
        if year is None:continue
        try:
            d=date(year,int(m.group('month')),int(m.group('day')))
        except ValueError:
            continue
        hour=m.group('hour');minute=m.group('minute')
        if hour is not None:
            h=int(hour);mi=int(minute or 0)
            if h==24 and mi==0:
                # 24:00 is a common official expression.  Keep its original
                # semantics without inventing a next-day instant.
                time_text='24:00'
            elif 0<=h<=23 and 0<=mi<=59:
                time_text=f'{h:02d}:{mi:02d}'
            else:
                time_text=None
        else:time_text=None
        out.append({'date':d.isoformat(),'time':time_text,'precision':'minute' if time_text else 'day','raw':m.group(0).strip()})
    return out


def _month(value: str) -> dict | None:
    m=_MONTH_RE.search(value)
    if not m:return None
    month=int(m.group('month'))
    if not 1<=month<=12:return None
    return {'date':f"{int(m.group('year')):04d}-{month:02d}",'time':None,'precision':'month','raw':m.group(0).strip()}


def _verified_evidence(resolver: EvidenceResolver, field: dict) -> tuple[str,list[dict]]:
    refs=field.get('evidence') if isinstance(field.get('evidence'),list) else []
    verified=[resolver.verify(x) for x in refs if isinstance(x,dict)]
    located=[x for x in verified if x.get('located')]
    return ('LOCATED' if located else 'UNLOCATED'),verified


def _point_supported(point: dict | None, evidence: list[dict]) -> bool:
    if not point or not point.get('date'):
        return False
    for ref in evidence:
        if not ref.get('located'):
            continue
        for quoted in _points(_norm(ref.get('quote'))):
            if quoted.get('date') != point.get('date'):
                continue
            # A date-only evidence quote cannot prove a model-produced clock
            # time.  Conversely a date-only milestone may be supported by a
            # more precise official quote on the same day.
            if point.get('time') and quoted.get('time') != point.get('time'):
                continue
            return True
    return False


def _rolling_supported(evidence: list[dict]) -> bool:
    return any(ref.get('located') and any(token in _norm(ref.get('quote')) for token in ROLLING_TOKENS) for ref in evidence)


def _milestone(kind: str,label: str,value: str,scope: str,field_key: str,state: str,evidence_support: str,evidence: list[dict],point: dict | None=None,*,historical=False,computable=False,end: dict | None=None) -> dict:
    point=point or {}
    row={
        'kind':kind,'label':label,'raw_value':value,'scope':scope,'field_key':field_key,
        'source_state':state,'evidence_support':evidence_support,'evidence':evidence,
        'date':point.get('date'),'time':point.get('time'),'precision':point.get('precision') or 'unresolved',
        'end_date':end.get('date') if end else None,'end_time':end.get('time') if end else None,
        'computable':bool(computable),'historical':bool(historical),'conflict':False,
    }
    return row


def evaluate_target_milestones(product: Any, session, target: CatalogTarget) -> dict:
    revision=session.get(Revision,target.revision_id)
    snapshot=session.get(Snapshot,revision.snapshot_id) if revision else None
    content=copy.deepcopy(target.content if isinstance(target.content,dict) else {})
    if not revision or not snapshot:
        return {'milestones':[],'time_readiness':{'state':'UNKNOWN','action_state':'UNKNOWN','reason':'EVIDENCE_CONTEXT_MISSING'},'deadline':None,'deadline_precision':None,'deadline_at':None,'primary_milestone':None}
    resolver=EvidenceResolver(product,revision,snapshot)
    currentness=content.get('currentness') if isinstance(content.get('currentness'),dict) else {}
    affected=set(currentness.get('affected_fields') or [])
    full_pending=target.status=='UPDATE_PENDING' and currentness.get('change_kind') in {'MISSING_PENDING','WITHDRAWAL_PENDING'}
    milestones=[];recognized=0
    for scope in ('fields','ancestor_fields','common_fields'):
        counts={}
        rows=content.get(scope) if isinstance(content.get(scope),list) else []
        for field in rows:
            if not isinstance(field,dict):continue
            label=_norm(field.get('label'));value=_norm(field.get('value'))
            counts[label]=counts.get(label,0)+1
            key=_field_key(scope,label,counts[label])
            if not label or not value or not _is_time_field(label,value):continue
            kind,mode,historical=_classification(label,value);recognized+=1
            source_state=str(field.get('state') or 'UNKNOWN').upper()
            support,evidence=_verified_evidence(resolver,field)
            pending=full_pending or key in affected or 'deadline' in affected
            safe_state=source_state in {'CONFIRMED','KNOWN'} and support=='LOCATED' and not pending
            points=_points(value)
            month=_month(value) if not points else None
            corrected=any(token in label for token in CORRECTED_TOKENS)
            precedence=(3 if scope=='fields' else 2 if scope=='ancestor_fields' else 1)+(2 if corrected else 0)
            if mode=='ROLLING':
                row=_milestone(kind,label,value,scope,key,source_state,support,evidence,historical=historical,computable=False)
                row.update(precedence=precedence,pending=pending,value_supported=_rolling_supported(evidence))
                milestones.append(row);continue
            if kind=='APPLICATION_WINDOW' and len(points)>=2:
                start,end=points[0],points[-1]
                a=_milestone('APPLICATION_OPEN',label,value,scope,key,source_state,support,evidence,start,historical=historical,computable=safe_state and not historical and _point_supported(start,evidence))
                b=_milestone('APPLICATION_DEADLINE',label,value,scope,key,source_state,support,evidence,end,historical=historical,computable=safe_state and not historical and _point_supported(end,evidence))
                a['value_supported']=_point_supported(start,evidence);b['value_supported']=_point_supported(end,evidence)
                for row in (a,b):row.update(precedence=precedence,pending=pending)
                milestones.extend((a,b));continue
            point=points[0] if points else month
            if mode=='WINDOW' and point and len(points)>=2:
                row=_milestone(kind,label,value,scope,key,source_state,support,evidence,points[0],historical=historical,computable=False,end=points[-1])
                row['value_supported']=_point_supported(points[0],evidence) and _point_supported(points[-1],evidence)
            else:
                supported=_point_supported(point,evidence)
                row=_milestone(kind,label,value,scope,key,source_state,support,evidence,point,historical=historical,computable=safe_state and supported and bool(point) and point.get('precision') in {'day','minute'})
                row['value_supported']=supported
            row.update(precedence=precedence,pending=pending)
            milestones.append(row)

    app=[m for m in milestones if m['kind']=='APPLICATION_DEADLINE' and not m['historical']]
    pending_time=full_pending or any(m.get('pending') for m in app)
    safe=[m for m in app if m['computable'] and not m.get('pending')]
    primary=None;conflict=False
    if safe:
        max_precedence=max(m.get('precedence',0) for m in safe)
        chosen=[m for m in safe if m.get('precedence',0)==max_precedence]
        values={(m.get('date'),m.get('time')) for m in chosen}
        if len(values)==1:
            primary=chosen[0]
        else:
            conflict=True
            for m in chosen:m['conflict']=True;m['computable']=False
    rolling=any(m['kind']=='ROLLING_APPLICATION' and not m['historical'] and m['source_state'] in {'CONFIRMED','KNOWN'} and m['evidence_support']=='LOCATED' and m.get('value_supported') for m in milestones)
    located_any=any(m['evidence_support']=='LOCATED' for m in milestones if not m['historical'])
    if pending_time:state='PENDING_UPDATE'
    elif conflict:state='CONFLICT'
    elif primary:state='READY'
    elif rolling:state='ROLLING'
    elif recognized or located_any:state='PARTIAL'
    else:state='UNKNOWN'
    deadline=primary.get('date') if primary else None
    precision=primary.get('precision') if primary else None
    deadline_at=None
    if primary and primary.get('date'):
        deadline_at=primary['date']+(('T'+primary['time']+':00+08:00') if primary.get('time') and primary['time']!='24:00' else '')
    today=date.today().isoformat()
    if state=='ROLLING':action_state='ROLLING'
    elif deadline and deadline<today:action_state='CLOSED'
    elif deadline:action_state='OPEN'
    else:action_state='UNKNOWN'
    readiness={'state':state,'action_state':action_state,'reason':{
        'READY':'PRIMARY_APPLICATION_DEADLINE_LOCATED','ROLLING':'ROLLING_APPLICATION_LOCATED','PARTIAL':'TIME_PRESENT_BUT_PRIMARY_DEADLINE_UNSAFE',
        'CONFLICT':'CONFLICTING_APPLICATION_DEADLINES','PENDING_UPDATE':'TIME_FIELD_UPDATE_PENDING','UNKNOWN':'NO_SAFE_TIME_SEMANTICS',
    }[state],'milestone_count':len(milestones)}
    public_milestones=[]
    for m in milestones:
        row={k:v for k,v in m.items() if k not in {'precedence','pending'}}
        public_milestones.append(row)
    primary_public=None
    if primary:
        primary_public={k:v for k,v in primary.items() if k not in {'precedence','pending'}}
    return {'milestones':public_milestones,'time_readiness':readiness,'deadline':deadline,'deadline_precision':precision,'deadline_at':deadline_at,'primary_milestone':primary_public}


def apply_target_milestones(product: Any, session, target: CatalogTarget) -> dict:
    projected=evaluate_target_milestones(product,session,target)
    body=copy.deepcopy(target.content if isinstance(target.content,dict) else {})
    body.update(projected)
    target.content=body
    return projected


def refresh_current_targets(product: Any, session) -> int:
    rows=list(session.scalars(select(CatalogTarget).where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))))
    changed=0
    for target in rows:
        before=(target.content or {}).get('time_readiness') if isinstance(target.content,dict) else None
        result=evaluate_target_milestones(product,session,target)
        if before!=result['time_readiness'] or any((target.content or {}).get(k)!=result[k] for k in ('milestones','deadline','deadline_precision','deadline_at','primary_milestone')):
            body=copy.deepcopy(target.content if isinstance(target.content,dict) else {})
            body.update(result);target.content=body;changed+=1
    return changed
