"""SG6.2 canonical qualification compiler.

The compiler turns WMA display facts into *candidate* canonical qualification
conditions.  It never approves a fact, never calls an LLM, and never decides
eligibility by itself.  Evidence resolution and final deterministic comparison
remain in :mod:`deepaha.product.eligibility`.
"""
from __future__ import annotations

import re
from typing import Any

EDUCATION_LEVELS={'专科':1,'大专':1,'高职':1,'本科':2,'大学本科':2,'硕士研究生':3,'硕士':3,'博士研究生':4,'博士':4}
DEGREE_LEVELS={'学士':1,'硕士':2,'博士':3}
EXCEPTION_TOKENS=('放宽','例外','除外','另有','或具有','或取得','符合其一','满足其一','以下情形之一','下列之一')
NONEXCLUSIVE_MAJOR_TOKENS=('等','相关专业','相近专业','类似专业','不限于','专业不限','不限专业')

ALIASES={
 'EDUCATION':{'学历','学历要求','最低学历','education','education_level','education_requirement','education_requirements'},
 'DEGREE':{'学位','学位要求','degree','degree_requirement','degree_requirements'},
 'MAJOR':{'专业','专业要求','专业条件','major','major_requirements','major_requirement','major_detail','major_code'},
 'GRADUATION':{'毕业届别','届别','招聘对象','招聘对象类别','recruit_object','recruitment_object','student_status'},
 'AGE':{'年龄','年龄要求','age','age_limit','age_requirement'},
 'HUKOU':{'户籍','户籍要求','生源地','household_registration','hukou','hukou_region'},
 'NATIONALITY':{'国籍','国籍要求','nationality','citizenship'},
 'POLITICAL':{'政治面貌','党员要求','political_status','political_requirement'},
 'EXPERIENCE':{'工作经历','工作经验','基层经历','相关经历','experience','work_experience','experience_requirement'},
 'CERTIFICATE':{'职业资格','资格证','证书','资格证书','certificate','certificates','certificate_requirement'},
 'TITLE':{'职称','专业技术职称','专业技术职务任职资格','professional_title','title_requirement'},
 'LANGUAGE':{'英语','外语','英语要求','外语要求','language_requirement','english_requirement','language_certificate'},
 'PARTICIPANT_SCOPE':{'参赛对象/资格','参赛对象','参与对象','申请对象范围-学校与届别','申请对象范围','applicant_scope','participant_scope'},
 'TEAM_SIZE':{'团队人数','团队人数上限','team_size','team_size_limit'},
 'APPLICATION_LIMIT':{'个人报名限制','报名队数限制','学校报名上限','application_limit'},
 'HARDSHIP':{'申请对象范围-七类困难条件（须符合下列之一）','困难条件','hardship_category'},
 'EMPLOYMENT_STATUS':{'是否须就业创业','就业创业状态','employment_status'},
}
QUALIFICATION_HINTS=('学历','学位','专业','年龄','户籍','生源','国籍','政治面貌','党员','工作经历','工作经验','基层经历','职业资格','资格证','证书','职称','英语','外语','招聘对象','届别','参赛对象','参赛资格','团队人数','报名限制','困难条件','就业创业')


def norm(value: Any) -> str:
    return ' '.join(str(value or '').replace('\r',' ').replace('\n',' ').split())


def label_key(label: str) -> str:
    return re.sub(r'[\s:：()（）/_-]+','',str(label or '')).casefold()

_ALIAS_LOOKUP={label_key(alias):kind for kind,aliases in ALIASES.items() for alias in aliases}


def canonical_kind(label: str) -> str | None:
    raw=str(label or '').strip()
    if raw in {'专业测评','专业测试','专业能力测评'}:
        return None
    key=label_key(raw)
    direct=_ALIAS_LOOKUP.get(key)
    if direct:return direct
    # Prefix/containment compatibility for labels such as “最低学历要求” or “英语六级要求”.
    for kind,aliases in ALIASES.items():
        for alias in aliases:
            if len(alias)>=2 and (alias in raw or (alias.isascii() and alias.casefold() in raw.casefold())):
                return kind
    if any(x in raw for x in QUALIFICATION_HINTS):return 'OTHER_HARD'
    return None


def _field_key(scope: str,label: str,occurrence: int) -> str:
    return f'{scope}:{label}#{occurrence}'


def _base(field: dict,scope: str,occurrence: int) -> dict:
    label=norm(field.get('label'));value=norm(field.get('value'))
    return {
      'field_id':field.get('id'),'field_key':_field_key(scope,label,occurrence),'label':label,'raw_value':value,
      'scope':scope,'hard':True,'state':str(field.get('state') or 'UNKNOWN').upper(),
      'evidence':field.get('evidence') if isinstance(field.get('evidence'),list) else [],
      'normalized':{},'type':'UNSUPPORTED_HARD_CONDITION','deterministic':False,
      'normalization_reason':'UNSUPPORTED_HARD_CONDITION','canonical_kind':canonical_kind(label),
    }


def _exception(value: str) -> bool:
    return any(token in value for token in EXCEPTION_TOKENS)


def _cn_int(value: str) -> int | None:
    digits={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    value=str(value or '').strip()
    if value in digits:return digits[value]
    if value=='十':return 10
    if '十' in value and len(value)<=3:
        left,right=value.split('十',1)
        tens=digits.get(left,1 if left=='' else None)
        ones=digits.get(right,0 if right=='' else None)
        if tens is not None and ones is not None:return tens*10+ones
    return None


def _education(value: str,base: dict) -> dict:
    if '不限' in value:
        base.update(type='EDUCATION_MIN',deterministic=True,normalized={'no_restriction':True},normalization_reason='NO_RESTRICTION');return base
    level=name=None
    for token,rank in sorted(EDUCATION_LEVELS.items(),key=lambda x:-len(x[0])):
        if token in value: level=rank;name=token;break
    if level is None:
        base.update(type='EDUCATION_MIN',normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base
    # A bare platform education value (“本科”) is safely usable as a *floor* for
    # rejecting lower education, but never as an exact-level exclusion of higher degrees.
    base.update(type='EDUCATION_MIN',deterministic=True,normalized={'minimum_level':level,'minimum_label':name},normalization_reason='NORMALIZED')
    return base


def _degree(value: str,base: dict) -> dict:
    if '不限' in value:
        base.update(type='DEGREE_MIN',deterministic=True,normalized={'no_restriction':True},normalization_reason='NO_RESTRICTION');return base
    for token,rank in sorted(DEGREE_LEVELS.items(),key=lambda x:-len(x[0])):
        if token in value:
            base.update(type='DEGREE_MIN',deterministic=True,normalized={'minimum_level':rank,'minimum_label':token},normalization_reason='NORMALIZED');return base
    base.update(type='DEGREE_MIN',normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base


def _major(value: str,base: dict) -> dict:
    if '不限' in value:
        base.update(type='MAJOR_CODE_SET',deterministic=True,normalized={'no_restriction':True,'allowed_prefixes':[]},normalization_reason='NO_RESTRICTION');return base
    codes=[]
    for x in re.findall(r'[（(]\s*(\d{2,8})\s*[)）]',value):
        if x not in codes:codes.append(x)
    # also accept API values that are plain numeric major/category codes
    for x in re.findall(r'(?<!\d)(\d{4,8})(?!\d)',value):
        if x not in codes:codes.append(x)
    if codes:
        base.update(type='MAJOR_CODE_SET',deterministic=True,normalized={'allowed_prefixes':codes,'exclusive':not any(t in value for t in NONEXCLUSIVE_MAJOR_TOKENS)},normalization_reason='NORMALIZED');return base
    # Keep semantic major restrictions visible to the computation lane instead of
    # discarding them, but do not use free-text similarity for hard denial.
    base.update(type='MAJOR_TEXT_REQUIREMENT',deterministic=False,normalized={'text':value},normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base


def _graduation(value: str,base: dict) -> dict:
    if '不限' in value:
        base.update(type='GRADUATION_YEAR_SET',deterministic=True,normalized={'no_restriction':True,'allowed_years':[]},normalization_reason='NO_RESTRICTION');return base
    if any(token in value for token in ('／','/','或')) and any(token in value for token in ('应届','在编','社会人员','招聘对象')):
        base.update(type='GRADUATION_YEAR_SET',deterministic=False,normalized={'text':value},normalization_reason='EXCEPTION_OR_ALTERNATIVE_PRESENT');return base
    years=sorted({int(x) for x in re.findall(r'(20\d{2})\s*届',value)})
    years += [int(x) for x in re.findall(r'(20\d{2})\s*年[^，。；;]{0,12}毕业',value) if int(x) not in years]
    if years:
        base.update(type='GRADUATION_YEAR_SET',deterministic=True,normalized={'allowed_years':years},normalization_reason='NORMALIZED');return base
    if any(x in value for x in ('应届生','应届毕业生','应届')):
        base.update(type='FRESH_GRADUATE_REQUIRED',deterministic=True,normalized={'required':True},normalization_reason='NORMALIZED');return base
    base.update(type='GRADUATION_YEAR_SET',normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base


def _age(value: str,base: dict,all_fields: list[dict]) -> dict | None:
    # education-specific cutoff matrix, common in enterprise recruitment notices.
    matrix={}
    for m in re.finditer(r'(大学本科|本科|硕士研究生|硕士|博士研究生|博士)[^；;。]{0,20}?(\d{4})年(\d{1,2})月(\d{1,2})日\s*及以后出生',value):
        matrix[str(EDUCATION_LEVELS[m.group(1)])]=f'{int(m.group(2)):04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}'
    if matrix:
        base.update(type='BIRTH_DATE_BY_EDUCATION',deterministic=True,normalized={'minimum_birth_dates':matrix},normalization_reason='NORMALIZED');return base
    cutoff=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*及以后出生',value)
    max_age=re.search(r'(\d{1,2})\s*周岁(?:及)?以下',value)
    explanatory=bool(cutoff and max_age and any(token in value for token in ('专指','岗位年龄条件','例如','其他以此类推')))
    if explanatory:return None
    if cutoff:
        base.update(type='BIRTH_DATE_MIN',deterministic=True,normalized={'minimum_birth_date':f'{int(cutoff[1]):04d}-{int(cutoff[2]):02d}-{int(cutoff[3]):02d}'},normalization_reason='NORMALIZED');return base
    if max_age:
        age=int(max_age[1]);helper=None;helper_evidence=[]
        for other in all_fields:
            if other is base:continue
            ov=norm(other.get('value'))
            if f'{age}周岁' not in ov:continue
            m=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*及以后出生',ov)
            if m and any(token in ov for token in ('专指','岗位年龄条件','例如','其他以此类推')):
                helper=f'{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}';helper_evidence=other.get('evidence') if isinstance(other.get('evidence'),list) else [];break
        if helper:
            base['evidence']=list(base['evidence'])+list(helper_evidence);base['support_mode']='ALL';base['required_evidence_count']=2
            base.update(type='BIRTH_DATE_MIN',deterministic=True,normalized={'minimum_birth_date':helper,'max_age':age},normalization_reason='NORMALIZED_WITH_AGE_CONTEXT');return base
        base.update(type='BIRTH_DATE_MIN',normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base
    base.update(type='BIRTH_DATE_MIN',normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base


def compile_field(field: dict,scope: str,occurrence: int,all_fields: list[dict]) -> dict | None:
    label=norm(field.get('label'));value=norm(field.get('value'))
    if not label or not value:return None
    kind=canonical_kind(label)
    if kind is None and label in {'其他条件','其他要求','备注','要求'}:
        # Generic composite cells are intentionally not split into hard rules here.
        # They remain visible and block positive coverage rather than risking a
        # false denial from one phrase embedded in a multi-clause condition.
        if any(x in value for x in QUALIFICATION_HINTS):kind='OTHER_HARD'
    if kind is None:return None
    base=_base(field,scope,occurrence)
    # OR/exception conditions remain candidates but cannot hard-deny automatically.
    if _exception(value):
        base['type']={'PARTICIPANT_SCOPE':'PARTICIPANT_SCOPE','HARDSHIP':'HARDSHIP_CATEGORY','APPLICATION_LIMIT':'APPLICATION_LIMIT'}.get(kind,'UNSUPPORTED_HARD_CONDITION')
        base['normalization_reason']='EXCEPTION_OR_ALTERNATIVE_PRESENT';return base
    if kind=='EDUCATION':return _education(value,base)
    if kind=='DEGREE':return _degree(value,base)
    if kind=='MAJOR':return _major(value,base)
    if kind=='GRADUATION':return _graduation(value,base)
    if kind=='AGE':return _age(value,base,all_fields)
    if kind=='HUKOU':
        if '不限' in value:base.update(type='HUKOU_REGION',deterministic=True,normalized={'no_restriction':True},normalization_reason='NO_RESTRICTION');return base
        regions=re.findall(r'([\u4e00-\u9fff]{2,12}(?:省|市|自治区|特别行政区))',value);regions=list(dict.fromkeys(regions))
        if regions:base.update(type='HUKOU_REGION',deterministic=True,normalized={'allowed_regions':regions},normalization_reason='NORMALIZED')
        else:base.update(type='HUKOU_REGION',normalization_reason='SEMANTIC_NOT_DETERMINISTIC')
        return base
    if kind=='NATIONALITY':
        if '不限' in value:base.update(type='NATIONALITY',deterministic=True,normalized={'no_restriction':True},normalization_reason='NO_RESTRICTION')
        elif any(x in value for x in ('中华人民共和国国籍','中国国籍','中国公民')):base.update(type='NATIONALITY',deterministic=True,normalized={'allowed':['中国']},normalization_reason='NORMALIZED')
        else:base.update(type='NATIONALITY',normalization_reason='SEMANTIC_NOT_DETERMINISTIC')
        return base
    if kind=='POLITICAL':
        if '不限' in value:base.update(type='POLITICAL_STATUS',deterministic=True,normalized={'no_restriction':True},normalization_reason='NO_RESTRICTION')
        elif '中共党员' in value or '预备党员' in value:
            allowed=['中共党员'];
            if '预备党员' in value or '含预备' in value:allowed.append('中共预备党员')
            base.update(type='POLITICAL_STATUS',deterministic=True,normalized={'allowed':allowed},normalization_reason='NORMALIZED')
        else:base.update(type='POLITICAL_STATUS',normalization_reason='SEMANTIC_NOT_DETERMINISTIC')
        return base
    if kind=='EXPERIENCE':
        if any(x in value for x in ('应届生','应届毕业生')):return _graduation(value,base)
        m=re.search(r'(\d+(?:\.\d+)?)\s*年(?:以上|及以上)?[^，。；;]{0,30}(?:工作|相关|经验|经历|训练)',value)
        if not m:m=re.search(r'(?:工作|相关|经验|经历|训练)[^，。；;]{0,30}(\d+(?:\.\d+)?)\s*年(?:以上|及以上)?',value)
        years=float(m.group(1)) if m else None
        if years is None:
            cm=re.search(r'([一二两三四五六七八九十]{1,3})\s*年(?:以上|及以上)?[^，。；;]{0,30}(?:工作|相关|经验|经历|训练)',value)
            if not cm:cm=re.search(r'(?:工作|相关|经验|经历|训练)[^，。；;]{0,30}([一二两三四五六七八九十]{1,3})\s*年(?:以上|及以上)?',value)
            parsed=_cn_int(cm.group(1)) if cm else None
            years=float(parsed) if parsed is not None else None
        if years is not None:base.update(type='EXPERIENCE_MIN_YEARS',deterministic=True,normalized={'minimum_years':years},normalization_reason='NORMALIZED')
        else:base.update(type='EXPERIENCE_REQUIREMENT',normalization_reason='SEMANTIC_NOT_DETERMINISTIC')
        return base
    if kind=='CERTIFICATE':base.update(type='CERTIFICATE_REQUIRED',deterministic=True,normalized={'required_text':value},normalization_reason='NORMALIZED');return base
    if kind=='TITLE':
        if '证书' in value or '资格考试' in value:
            base.update(type='CERTIFICATE_REQUIRED',deterministic=True,normalized={'required_text':value},normalization_reason='NORMALIZED')
        else:
            base.update(type='TITLE_REQUIRED',deterministic=True,normalized={'required_text':value},normalization_reason='NORMALIZED')
        return base
    if kind=='LANGUAGE':base.update(type='LANGUAGE_CERTIFICATE',deterministic=True,normalized={'required_text':value},normalization_reason='NORMALIZED');return base
    if kind=='PARTICIPANT_SCOPE':
        levels=[]
        for token,token_levels in [('高职高专',(1,)),('专科',(1,)),('本科生',(2,)),('本科',(2,)),('研究生',(3,4)),('硕士',(3,)),('博士',(4,))]:
            if token in value:
                for level in token_levels:
                    if level not in levels:levels.append(level)
        base.update(type='PARTICIPANT_SCOPE',deterministic=bool(levels),normalized={'education_levels':levels,'text':value},normalization_reason='NORMALIZED' if levels else 'SEMANTIC_NOT_DETERMINISTIC');return base
    if kind=='TEAM_SIZE':
        nums=[int(x) for x in re.findall(r'(?:不超过|最多|上限)\s*(\d+)\s*人',value)]
        base.update(type='TEAM_SIZE_MAX',deterministic=len(set(nums))==1,normalized={'maximum':nums[0]} if len(set(nums))==1 else {'text':value},normalization_reason='NORMALIZED' if len(set(nums))==1 else 'SEMANTIC_NOT_DETERMINISTIC');return base
    if kind=='APPLICATION_LIMIT':base.update(type='APPLICATION_LIMIT',normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base
    if kind=='HARDSHIP':base.update(type='HARDSHIP_CATEGORY',normalization_reason='EXCEPTION_OR_ALTERNATIVE_PRESENT');return base
    if kind=='EMPLOYMENT_STATUS':base.update(type='EMPLOYMENT_STATUS',normalization_reason='SEMANTIC_NOT_DETERMINISTIC');return base
    return base


def is_qualification_field(field: dict) -> bool:
    return canonical_kind(norm(field.get('label'))) is not None


COMPILER_PROJECTION_VERSION = 1


def summarize_content(content: dict) -> dict:
    """Build deterministic, rebuildable compiler metadata for a CatalogTarget.

    The summary is intentionally *pre-evidence*: it describes what the compiler
    can classify from the accepted WMA projection, but it never claims that a
    condition is evidence-located or safe for a formal eligibility decision.
    Evidence is always re-verified by :mod:`deepaha.product.eligibility`.
    """
    all_raw=[]
    flattened=[]
    for scope in ('fields','ancestor_fields','common_fields'):
        counts={}
        for field in content.get(scope,[]) if isinstance(content.get(scope),list) else []:
            if not isinstance(field,dict):
                continue
            label=norm(field.get('label'))
            counts[label]=counts.get(label,0)+1
            flattened.append((scope,field,counts[label]))
            all_raw.append(field)
    candidates=[]
    for scope,field,occ in flattened:
        cand=compile_field(field,scope,occ,all_raw)
        if cand:
            candidates.append(cand)
    canonical_types=sorted({str(c.get('type')) for c in candidates if c.get('type')})
    deterministic=sum(1 for c in candidates if c.get('deterministic'))
    unresolved=sum(1 for c in candidates if not c.get('deterministic') or c.get('type')=='UNSUPPORTED_HARD_CONDITION')
    return {
        'version':COMPILER_PROJECTION_VERSION,
        'canonical_condition_count':len(candidates),
        'deterministic_condition_count':deterministic,
        'unresolved_condition_count':unresolved,
        'canonical_types':canonical_types,
        'source_coverage':str(content.get('qualification_coverage') or '').upper() or None,
        'evidence_verified':False,
    }
