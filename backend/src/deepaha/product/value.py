"""SG5 local Opportunity Value / Priority engine.

This module intentionally does not call an LLM.  It ranks a bounded candidate
pool using explicit user state, SG4 eligibility, current target data and safe
calendar information.  Numeric scores are an internal ordering detail and are
never part of the public result contract.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

PERSONALIZABLE_TYPES = {
    'PUBLIC_INSTITUTION_JOB','STATE_OWNED_ENTERPRISE_JOB','CIVIL_SERVICE','GRASSROOTS_PROGRAM',
    'YOUTH_POLICY_BENEFIT','POSTGRAD_RECOMMENDATION','ADMISSION_CHANGE','COMPETITION',
    'RESEARCH_PROGRAM','SCHOLARSHIP','YOUTH_DEVELOPMENT_PROGRAM',
}

TYPE_NAMES = {
    'PUBLIC_INSTITUTION_JOB':'事业单位','STATE_OWNED_ENTERPRISE_JOB':'国央企','CIVIL_SERVICE':'考公',
    'GRASSROOTS_PROGRAM':'基层项目','YOUTH_POLICY_BENEFIT':'人才政策','POSTGRAD_RECOMMENDATION':'升学',
    'ADMISSION_CHANGE':'招生信息','COMPETITION':'竞赛','RESEARCH_PROGRAM':'科研','SCHOLARSHIP':'奖学金',
    'YOUTH_DEVELOPMENT_PROGRAM':'成长与实践',
}

TYPE_HINTS = {
    'PUBLIC_INSTITUTION_JOB':('事业单位','招聘','岗位'),
    'STATE_OWNED_ENTERPRISE_JOB':('国企','央企','国央企','招聘'),
    'CIVIL_SERVICE':('公务员','考公','招录'),
    'GRASSROOTS_PROGRAM':('基层','选调','三支一扶'),
    'YOUTH_POLICY_BENEFIT':('政策','补贴','人才政策','支持','安居'),
    'POSTGRAD_RECOMMENDATION':('保研','推免','夏令营','升学','研究生'),
    'ADMISSION_CHANGE':('招生','升学'),
    'COMPETITION':('竞赛','比赛','赛道','挑战赛'),
    'RESEARCH_PROGRAM':('科研','研究','实验室','课题'),
    'SCHOLARSHIP':('奖学金','资助','奖项'),
    'YOUTH_DEVELOPMENT_PROGRAM':('实践','实习','项目','训练营','见习'),
}

# Deliberately small transparent vocabulary.  It is used only for retrieval and
# value explanation; it never changes official facts or SG4 eligibility.
SEMANTIC_HINTS = (
    'AI','AIGC','人工智能','产品','运营','内容','传播','广告','设计','写作','数据','Python','编程',
    '科研','研究','实验室','课题','竞赛','比赛','赛道','创新','创业','项目','实践','实习','见习',
    '政策','补贴','人才','安居','就业','求职','国企','央企','事业单位','公务员','考公',
    '保研','推免','夏令营','奖学金','资助','管理','教师','技术','工程','医疗','健康','安全',
)

def _norm(value: Any) -> str:
    return re.sub(r'\s+', '', str(value or '')).casefold()


def _text(content: dict) -> str:
    parts=[content.get('title'),content.get('summary'),content.get('issuer'),content.get('region'),content.get('raw_type')]
    for scope in ('fields','ancestor_fields','common_fields'):
        for field in content.get(scope) or []:
            if isinstance(field,dict):
                parts.extend((field.get('label'),field.get('value')))
    return ' '.join(str(x) for x in parts if x not in ('',None))


def _tokens(values) -> list[str]:
    out=[]
    for value in values or []:
        raw=str(value or '').strip()
        if not raw: continue
        out.append(raw)
        folded=raw.casefold()
        for hint in SEMANTIC_HINTS:
            if hint.casefold() in folded:
                out.append(hint)
        for english in re.findall(r'[A-Za-z][A-Za-z0-9+#.-]{1,24}',raw):
            out.append(english)
    # preserve order; avoid 1-character noisy Chinese fragments
    return list(dict.fromkeys(x for x in out if len(x.strip())>=2 or x.upper() in {'AI'}))


def _region_match(region: str, cities) -> bool:
    r=_norm(region)
    if not r:return False
    for city in cities or []:
        c=_norm(city)
        if c and (c in r or r in c):return True
    return False




def inferred_types(profile: dict) -> list[str]:
    """Infer broad opportunity-type interests from progressive user state.

    This is only a retrieval hint.  It never changes opportunity facts or SG4
    eligibility and it never acts as a hard filter unless the user explicitly
    selected opportunity_types.
    """
    text=' '.join((profile.get('interests') or [])+(profile.get('goals') or [])+(profile.get('career_directions') or [])).casefold()
    out=[]
    for typ,hints in TYPE_HINTS.items():
        if any(h.casefold() in text for h in hints):out.append(typ)
    return out

def retrieval_score(content: dict, profile: dict) -> int:
    """Cheap first-stage score used before evidence-backed eligibility work."""
    score=0
    body=_norm(_text(content))
    typ=content.get('type')
    selected=set(profile.get('opportunity_types') or [])
    inferred=set(inferred_types(profile))
    if selected and typ in selected:score+=12
    elif selected and typ not in selected:score-=20
    elif inferred and typ in inferred:score+=7
    if _region_match(content.get('region',''),profile.get('cities')):score+=6
    for term in _tokens(profile.get('career_directions')): score+=4 if _norm(term) in body else 0
    for term in _tokens(profile.get('goals')): score+=3 if _norm(term) in body else 0
    for term in _tokens(profile.get('interests')): score+=2 if _norm(term) in body else 0
    for term in _tokens(profile.get('skills')): score+=1 if _norm(term) in body else 0
    hints=TYPE_HINTS.get(typ,())
    interest_body=' '.join(profile.get('interests',[])+profile.get('goals',[])+profile.get('career_directions',[])).casefold()
    if any(h.casefold() in interest_body for h in hints):score+=3
    return score


def _deadline(content: dict):
    raw=content.get('deadline')
    if not raw:return None,None
    try:
        day=date.fromisoformat(str(raw));return day,(day-date.today()).days
    except ValueError:return None,None


def assess(content: dict, profile: dict, eligibility: dict, *, action_status=None, negative_feedback=False) -> dict:
    """Return public explanation plus private `_score` for deterministic ordering."""
    score=0;why=[];risks=[];features=[]
    status=eligibility.get('status') or 'UNCERTAIN'
    typ=content.get('type') or ''
    type_name=TYPE_NAMES.get(typ,'这类机会')
    selected=set(profile.get('opportunity_types') or [])

    qualification_gate='NORMAL'
    qualification_risk=(eligibility.get('qualification_risk') or {}).get('level') or 'NORMAL'
    if status=='ELIGIBLE':
        score+=8;features.append('资格条件明确符合');why.append('当前已计算的资格条件明确符合。')
    elif status=='LIKELY_ELIGIBLE':
        score+=6;features.append('已知硬条件未发现冲突');why.append('当前可计算的硬条件没有发现冲突。')
    elif status=='UNCERTAIN':
        score+=1;risks.append('仍有资格条件不能安全自动判断，需查看官方条件。')
        if qualification_risk=='HIGH':
            # Keep the official eligibility state UNCERTAIN.  This is only a
            # recommendation gate: a deterministic conflict signal whose
            # evidence is not strong enough for SG4 denial must not occupy the
            # scarce headline Top-N, but remains visible for exploration.
            qualification_gate='HOLD_FOR_CONFIRMATION'
            score-=20
            risks.insert(0,'材料中存在与你画像明显冲突的资格线索，但证据尚不足以正式判定不符合；建议先核对官方条件。')
    elif status=='INELIGIBLE':
        score-=100;risks.append('当前官方证据支持至少一项明确硬条件冲突。')

    inferred=set(inferred_types(profile))
    if selected and typ in selected:
        score+=8;features.append('机会类型偏好');why.append(f'这是你主动关注的{type_name}类机会。')
    elif not selected and typ in inferred:
        score+=5;features.append('画像推断的机会类型');why.append(f'你填写的关注方向与{type_name}类机会直接相关。')

    region=content.get('region') or ''
    cities=profile.get('cities') or []
    if cities:
        if _region_match(region,cities):
            score+=5;features.append('地区偏好');why.append(f'地点与你关注的{next((c for c in cities if _norm(c) in _norm(region) or _norm(region) in _norm(c)),cities[0])}有关。')
        elif region:
            if profile.get('region_preference_mode')=='PREFERRED':score-=2
            risks.append(f'地点是{region}，与你当前关注城市不完全一致。')
        else:
            risks.append('当前材料没有明确可用于排序的地区信息。')

    body=_norm(_text(content));matched=set()
    groups=[('当前目标',profile.get('goals'),3),('发展方向',profile.get('career_directions'),3),('兴趣',profile.get('interests'),2),('技能',profile.get('skills'),1)]
    for label,values,weight in groups:
        for term in _tokens(values):
            if _norm(term) in body and term.casefold() not in matched:
                matched.add(term.casefold());score+=weight;features.append(f'{label}:{term}');why.append(f'内容与你的{label}“{term}”有直接关联。')
                if len(why)>=5:break

    # Type-level semantic hint is weaker than an exact content match, but helps
    # a profile saying “科研/政策/竞赛” even if a child card omits that word.
    profile_text=' '.join((profile.get('interests') or [])+(profile.get('goals') or [])+(profile.get('career_directions') or [])).casefold()
    if any(h.casefold() in profile_text for h in TYPE_HINTS.get(typ,())) and not any('机会类型偏好'==x for x in features):
        score+=2;features.append('方向与机会类别相关');why.append(f'这类{type_name}与你填写的关注方向相关。')

    day,days=_deadline(content)
    if day is None:
        for req in eligibility.get('requirements') or []:
            if req.get('type')=='APPLICATION_DEADLINE' and req.get('evidence_support')=='LOCATED' and req.get('normalized',{}).get('deadline'):
                try:
                    day=date.fromisoformat(req['normalized']['deadline']);days=(day-date.today()).days
                except ValueError:
                    day=days=None
                break
    if days is None:
        why_now='时间节点尚未明确，先确认当前官方安排。'
        risks.append('当前没有可靠的精确截止时间。')
    elif days < 0:
        score-=100;why_now='当前记录的申请窗口已经结束。';risks.append('申请窗口已结束。')
    elif days <= 3:
        score+=7;why_now=f'报名窗口只剩 {days} 天，需要立即确认材料和入口。';features.append('截止临近')
    elif days <= 14:
        score+=5;why_now=f'报名窗口剩 {days} 天，已经进入值得安排准备的时间段。';features.append('近期截止')
    elif days <= 30:
        score+=3;why_now=f'距离报名截止还有 {days} 天，现在适合开始准备。';features.append('30天内截止')
    elif days <= 60:
        score+=1;why_now=f'距离报名截止还有 {days} 天，可以提前准备关键材料。'
    else:
        why_now=f'当前已知截止还有 {days} 天，暂不需要抢时间，但可以提前了解。'

    if content.get('status')=='UPDATE_PENDING':
        score-=4;risks.append('来源有更新等待收录，受影响内容暂不用于精确行动判断。')
    if action_status=='SAVED':
        score+=1;features.append('你已收藏')
    if negative_feedback:
        score-=8;risks.append('你之前曾反馈这项机会暂时不适合。')

    # Constraints are preserved in User State but free text does not become an
    # automatic hard filter in SG5.  Surface the boundary instead.
    if profile.get('constraints'):
        risks.append('你填写了个人限制条件；SG5 不会把自由文本限制自动转换成硬资格规则。')

    if status=='INELIGIBLE' or days is not None and days < 0:
        band='NOT_RECOMMENDED'
    elif days is not None and 0<=days<=14 and score>=12:
        band='ACT_NOW'
    elif score>=12:
        band='HIGH'
    elif score>=6:
        band='RELEVANT'
    else:
        band='EXPLORE'

    public={
        'target_id':content.get('id'),
        'priority_band':band,
        'value_band':'STRONG' if score>=12 else 'RELEVANT' if score>=6 else 'DISCOVERY',
        'eligibility_status':status,
        'qualification_gate':qualification_gate,
        'why_for_you':list(dict.fromkeys(why))[:4] or ['这是一个可以进一步了解的具体机会。'],
        'why_now':why_now,
        'risks':list(dict.fromkeys(risks))[:4] or ['提交或报名之前仍应查看最新官方材料。'],
        'features':list(dict.fromkeys(features))[:8],
        'basis':'LOCAL_VALUE_PRIORITY_V1',
        'llm_used':False,
        'personalization_enabled':profile.get('personalization_enabled',True) is not False,
    }
    public['_score']=score
    return public


def public_assessment(value: dict) -> dict:
    return {k:v for k,v in value.items() if not k.startswith('_')}


def diversify(items: list[dict], count=3) -> list[dict]:
    """Prefer distinct roots in the headline Top-N; fill deterministically."""
    selected=[];roots=set()
    for item in items:
        root=item.get('root_public_id') or item.get('id')
        if root in roots:continue
        selected.append(item);roots.add(root)
        if len(selected)>=count:return selected
    for item in items:
        if item in selected:continue
        selected.append(item)
        if len(selected)>=count:break
    return selected
