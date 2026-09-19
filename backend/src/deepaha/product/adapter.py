"""Bounded, loss-aware display projection. Not a factual-certification engine.
WMA's CONFIRMED is an agent claim. Only byte hashes and exact textual quote
location are checked locally. Neither operation grants eligibility authority.
"""
import hashlib
import ipaddress
import json
import math
from collections import Counter
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlsplit
from pathlib import PurePosixPath
from .errors import Problem

ADAPTER_VERSION='overview-display/3.5.0'
MAX_TEXT=12000
MAX_ENTRIES=10000
TYPE_MAP={'招聘':'PUBLIC_INSTITUTION_JOB','校招':'STATE_OWNED_ENTERPRISE_JOB','实习':'YOUTH_DEVELOPMENT_PROGRAM',
          '竞赛':'COMPETITION','比赛':'COMPETITION','人才政策':'YOUTH_POLICY_BENEFIT','人才补贴':'YOUTH_POLICY_BENEFIT',
          '补贴':'YOUTH_POLICY_BENEFIT','政策':'YOUTH_POLICY_BENEFIT','科研':'RESEARCH_PROGRAM','奖学金':'SCHOLARSHIP',
          '推免':'POSTGRAD_RECOMMENDATION','保研':'POSTGRAD_RECOMMENDATION','夏令营':'POSTGRAD_RECOMMENDATION',
          '升学':'POSTGRAD_RECOMMENDATION','社会实践':'YOUTH_DEVELOPMENT_PROGRAM','实践计划':'YOUTH_DEVELOPMENT_PROGRAM'}
TYPES={'PUBLIC_INSTITUTION_JOB','STATE_OWNED_ENTERPRISE_JOB','CIVIL_SERVICE','GRASSROOTS_PROGRAM',
       'YOUTH_POLICY_BENEFIT','POSTGRAD_RECOMMENDATION','ADMISSION_CHANGE','COMPETITION','RESEARCH_PROGRAM',
       'SCHOLARSHIP','YOUTH_DEVELOPMENT_PROGRAM'}
DENY_KEYS={'password','token','api_key','authorization','internal_note','internal_notes','debug','trace','stack','reviewer','reviewer_id','raw_manifest'}
ROOT_FIELDS={'publish_date':'公告发布时间','registration_start':'报名开始','registration_deadline':'报名截止',
 'work_location':'工作地点','application_method':'申请方式','official_contact':'官方联系方式','benefit':'支持内容',
 'eligibility':'申请条件','application_materials':'申请材料','notes':'其他说明'}


def safe_url(value):
    if not isinstance(value,str) or len(value)>3000:return None
    try:
        u=urlsplit(value.strip())
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password:return None
        host=u.hostname.lower().rstrip('.')
        if host=='localhost' or host.endswith(('.local','.internal','.localhost')):return None
        try:
            if not ipaddress.ip_address(host).is_global:return None
        except ValueError:pass
        if u.port and u.port not in (80,443):return None
        if any(ord(c)<32 for c in value):return None
        return value.strip()
    except ValueError:return None

def display_value(value):
    """Remove explicitly private structured keys, not ordinary business wording."""
    if isinstance(value,dict):
        return {k:display_value(v) for k,v in value.items() if k.lower() not in DENY_KEYS}
    if isinstance(value,list):return [display_value(v) for v in value]
    return value

def text(v,limit=MAX_TEXT):
    if v is None:return ''
    if not isinstance(v,str):v=json.dumps(v,ensure_ascii=False,separators=(',',':'))
    return v[:limit].replace('\x00','')

def hash_json(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def parse_json(b):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('duplicate json key')
            d[k]=v
        return d
    value=json.loads(b.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('non-finite JSON value')))
    def walk(v,depth=0):
        if depth>40:raise ValueError('nested too deeply')
        if isinstance(v,float) and not math.isfinite(v):raise ValueError('non-finite numeric value')
        if isinstance(v,dict):
            for x in v.values():walk(x,depth+1)
        elif isinstance(v,list):
            for x in v:walk(x,depth+1)
    walk(value)
    return value

class HTMLText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','template'):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','template'):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def searchable(b,name):
    # Never make OCR or third-party network requests here. Unsupported binary
    # documents retain references but their quotes remain unlocated.
    ext=PurePosixPath(name).suffix.lower()
    if ext not in ('.txt','.md','.html','.htm','.json','.csv','.xml'):return None
    try:s=b.decode('utf-8-sig')
    except UnicodeDecodeError:return None
    if ext in ('.html','.htm'):
        p=HTMLText();p.feed(s);s='\n'.join(p.parts)
    return re.sub(r'\s+',' ',s)

def exact_day(v):
    t=v.strip()
    m=re.fullmatch(r'(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?',t)
    if not m:return None
    try:return date(*map(int,m.groups())).isoformat()
    except ValueError:return None

def category(raw):
    r=text(raw,100)
    if r in TYPES:return r
    for cn,en in TYPE_MAP.items():
        if cn in r:return en
    return 'YOUTH_DEVELOPMENT_PROGRAM'

def lifecycle_status(*values):
    """Normalize only explicit lifecycle claims; absence never means withdrawal."""
    for value in values:
        token=str(value or '').strip().upper()
        if token in {'WITHDRAWN','RETRACTED','CANCELLED','CANCELED','撤回','取消','已撤回','已取消'}:
            return 'WITHDRAWN'
        if token in {'ACTIVE','CURRENT','OPEN','有效','正常','开放'}:
            return 'ACTIVE'
    return 'ACTIVE'


def section_for(label):
    if any(x in label for x in ['报名','截止','时间','赛程','日期']):return '时间与办理'
    if any(x in label for x in ['学历','专业','资格','条件','年龄','届','组队','服务期']):return '条件与限制'
    if any(x in label for x in ['奖励','待遇','金额','支持','补贴','兑付']):return '支持与回报'
    if any(x in label for x in ['权利','知识产权','作品']):return '作品与权利'
    return '其他说明'


def project(files,source,notice_url=None):
    blockers=[];notes=[];artifacts=[];artifact_lookup={};num_fields=0;excluded_objects=[]
    evidence={}
    try:
        evidence=parse_json(files.get('evidence.json',b'{}'))
        if not isinstance(evidence,dict):raise ValueError()
    except (ValueError,TypeError,RecursionError):notes.append('证据目录未能读取；相关内容保留，引用位置尚未确认。');evidence={}
    raw_arts=evidence.get('artifacts',[])
    if not isinstance(raw_arts,list):raw_arts=[];notes.append('证据目录格式不完整。')
    for i,a in enumerate(raw_arts[:MAX_ENTRIES]):
        if not isinstance(a,dict):continue
        aid=text(a.get('artifact_id') or a.get('id') or f'artifact-{i}',128)
        path=a.get('local_path') or a.get('path') or a.get('file_path') or a.get('filename')
        if isinstance(path,str) and path not in files:
            # Remote workspace paths map only by a unique suffix, never basename guessing.
            matches=[k for k in files if path.endswith('/'+k)]
            if len(matches)==1:path=matches[0]
        path=path if isinstance(path,str) and path in files else None
        declared=a.get('sha256') or a.get('hash')
        actual=hashlib.sha256(files[path]).hexdigest() if path else None
        integrity='MATCH' if path and (not declared or declared==actual) else ('MISMATCH' if path else 'MISSING')
        url=safe_url(a.get('url') or a.get('source_url') or a.get('original_url'))
        state=text(a.get('status') or ('已保存' if path else '未取得'),80)
        row={'id':aid,'name':text(a.get('name') or path or f'材料 {i+1}',180),'url':url,'path':path,
             'sha256':actual,'integrity':integrity,'state':state}
        artifacts.append(row);artifact_lookup[aid]=row
        if integrity=='MISMATCH':
            notes.append(f'材料“{row["name"]}”的文件校验不一致，相关引用不用于计算。')
            if a.get('critical') is True:blockers.append('核心原件完整性校验失败，无法可靠使用本份返回。')
        elif integrity=='MISSING':notes.append(f'材料“{row["name"]}”未取得，涉及条件可能不完整。')
    def fact(f,index,target='common'):
        nonlocal num_fields
        num_fields+=1
        if num_fields>MAX_ENTRIES:raise Problem('本次内容超过10000个条目，请拆分返回包',413)
        if not isinstance(f,dict):f={'field':'其他内容','value':f}
        label=text(f.get('field') or f.get('label') or f.get('name') or '其他说明',180)
        if label.lower() in DENY_KEYS:return None
        value=text(display_value(f.get('value',f.get('raw_value',f.get('text','')))),100_000_000)
        state=text(f.get('status') or f.get('state') or 'UNKNOWN',80).upper()
        raw_e=f.get('evidence',f.get('references',[]))
        if isinstance(raw_e,dict):raw_e=[raw_e]
        if not isinstance(raw_e,list):raw_e=[]
        refs=[];located=False
        for e in raw_e[:30]:
            if not isinstance(e,dict):continue
            aid=text(e.get('artifact_id') or e.get('id') or '',128)
            a=artifact_lookup.get(aid)
            quote=text(e.get('quote') or '',4000)
            found=False
            if a and a['path'] and a['integrity']=='MATCH' and quote:
                readable=searchable(files[a['path']],a['path'])
                found=readable is not None and re.sub(r'\s+',' ',quote).strip() in readable
            located|=found
            locator=e.get('locator')
            if isinstance(locator,dict):locator={k:text(v,160) for k,v in locator.items() if k in ('sheet','row','column','cell','page','line','section','paragraph','table')}
            else:locator={}
            refs.append({'artifact_id':aid,'quote':quote,'locator':locator,'located':found,'url':a['url'] if a else safe_url(e.get('url'))})
        note=text(f.get('note') or '',2000)
        warnings=[]
        if note:warnings.append(note)
        excluded=state in ('INVALID','PROVEN_WRONG','RETRACTED','EXCLUDED')
        if excluded:warnings.append('原始返回将此条目标为不可采用。')
        elif state=='CONFLICT':warnings.append('材料存在不同表述，请结合各自来源确认。')
        elif state in ('UNPROCESSED','UNREAD','NOT_EXTRACTED'):warnings.append('此项尚未完成材料读取或提取。')
        elif state in ('NOT_STATED','NOT_FOUND'):warnings.append('仅在本次已读材料中未找到说明，不代表没有要求。')
        if not located and value and not excluded:warnings.append('尚未在已保存原件中定位此项引用。')
        # Capability independent of WMA confidence; no inferred hard eligibility.
        return {'id':hash_json([source['id'],target,index,label])[:24], 'label':label,'value':value,
                'state':state,'section':section_for(label),'notes':list(dict.fromkeys(warnings)),
                'evidence':refs,'quote_located':located,'excluded':excluded,
                'usage':{'display':not excluded,'qualification':False,'date_action':located and state not in ('CONFLICT','UNKNOWN','INSUFFICIENT','UNPROCESSED','NOT_EXTRACTED','UNREAD')},
                'target':target}
    def rows(lst,target):
        if isinstance(lst,dict):lst=[{'field':k,'value':v} for k,v in lst.items()]
        if not isinstance(lst,list):return []
        out=[]
        for i,f in enumerate(lst):
            v=fact(f,i,target)
            if v:out.append(v)
        return out
    try:
        raw=parse_json(files.get('opportunities.json',b''))
        roots=raw if isinstance(raw,list) else raw.get('opportunities',[raw]) if isinstance(raw,dict) else []
        if not isinstance(roots,list):roots=[roots]
    except (ValueError,TypeError,RecursionError):
        roots=[];blockers.append('结构化结果无法安全读取；原始报告和文件已保留。')
    if not roots:blockers.append('尚无法确定本次返回对应的机会对象。')
    opportunities=[]
    url_counts=Counter(safe_url(x.get('official_url') or x.get('notice_url') or x.get('source_url') or notice_url) for x in roots if isinstance(x,dict))
    for ri,r in enumerate(roots[:1000]):
        if not isinstance(r,dict):notes.append(f'第{ri+1}项内容无法读取。');continue
        title=text(r.get('opportunity_name') or r.get('title') or r.get('name') or '',600)
        if not title.strip():
            excluded_objects.append({'index':ri,'title':'未辨识条目','reason':'没有可辨识的机会名称'})
            notes.append(f'第{ri+1}项没有可辨识的机会名称，未纳入收录范围。');continue
        url=safe_url(r.get('official_url') or r.get('notice_url') or r.get('source_url') or notice_url)
        if not url and artifacts:url=next((a['url'] for a in artifacts if a['url']),None)
        if not url:url=source['url']
        host=urlsplit(url).hostname
        if host not in source['allowed_hosts']:
            excluded_objects.append({'index':ri,'title':title,'reason':'主要来源无法归属到已允许的机构入口'})
            notes.append(f'“{title}”的主要来源无法归属到本次允许的机构，未纳入收录范围。');continue
        fs=rows(r.get('announcement_level',r.get('fields',r.get('facts',[]))),f'root-{ri}')
        for key,label in ROOT_FIELDS.items():
            if r.get(key) is not None and not any(f['label']==label and f['value']==text(r[key]) for f in fs):
                f=fact({'field':label,'value':r[key]},key,f'root-{ri}')
                if f:fs.append(f)
        children=[]
        def child(c,ci,parent=None,default_kind='POSITION',depth=0):
            if depth>4:
                extra=fact({'field':'较深层级的原始内容','value':c},f'deep/{ci}',f'root-{ri}')
                if extra:fs.append(extra)
                return
            if not isinstance(c,dict):return
            producer_id=c.get('id')
            stable_source_key=c.get('source_record_key')
            ident=text(stable_source_key or producer_id or f'child-{ci}',128)
            kind=text(c.get('kind') or c.get('type') or default_kind,40).upper()
            kind=kind if kind in ('POSITION','TRACK','PROGRAM_TIER','REGION_VARIANT','GROUP','DEFAULT_SINGLETON') else default_kind
            cf=rows(c.get('facts',c.get('fields',c.get('unit_level',[]))),f'root-{ri}/{ci}/{ident}')
            for k,v in c.items():
                if k not in {'id','source_record_key','name','kind','type','facts','fields','unit_level','positions','children','tracks','program_tiers','tiers','region_variants','action_units','parent_id','code','application_url','official_url','region','summary','lifecycle_status','opportunity_status','status'} and k.lower() not in DENY_KEYS:
                    extra=fact({'field':k,'value':v},f'extra/{k}',f'root-{ri}/{ci}/{ident}')
                    if extra:cf.append(extra)
            identity_source='SOURCE_RECORD_KEY' if stable_source_key else ('PRODUCER_ID' if producer_id else 'FALLBACK_PATH')
            children.append({'id':hash_json([ri,ci,ident])[:24],'source_key':ident,'identity_source':identity_source,
               'source_path':f'root-{ri}/{ci}/{ident}','name':text(c.get('name') or '未命名条目',300),
               'kind':kind,'parent_id':parent,'fields':cf,'code':text(c.get('code') or '',80),
               'application_url':safe_url(c.get('application_url')),'official_url':safe_url(c.get('official_url')),
               'region':text(c.get('region') or '',300),'summary':text(c.get('summary') or '',2000),
               'lifecycle_status':lifecycle_status(c.get('lifecycle_status'),c.get('opportunity_status'),c.get('status'))})
            parent_key=children[-1]['id']
            for group,d_kind in [('positions','POSITION'),('tracks','TRACK'),('program_tiers','PROGRAM_TIER'),('tiers','PROGRAM_TIER'),('region_variants','REGION_VARIANT'),('action_units','DEFAULT_SINGLETON'),('children','DEFAULT_SINGLETON')]:
                for j,x in enumerate(c.get(group,[]) if isinstance(c.get(group,[]),list) else []):child(x,f'{ci}/{j}',parent_key,d_kind,depth+1)
        for key,kind in [('units','GROUP'),('positions','POSITION'),('tracks','TRACK'),('program_tiers','PROGRAM_TIER'),('tiers','PROGRAM_TIER'),('region_variants','REGION_VARIANT'),('action_units','DEFAULT_SINGLETON'),('children','DEFAULT_SINGLETON')]:
            for ci,c in enumerate(r.get(key,[]) if isinstance(r.get(key,[]),list) else []):child(c,f'{key}/{ci}',default_kind=kind)
        consumed=set(ROOT_FIELDS)|{'opportunity_name','name','title','publish_unit','issuer','opportunity_type','type','category',
          'official_url','notice_url','source_url','source_record_key','id','announcement_level','fields','facts','units','positions','tracks','program_tiers','tiers','region_variants','action_units','children','metadata','summary','region','application_url','lifecycle_status','opportunity_status','status'}
        for k,v in r.items():
            if k not in consumed and k.lower() not in DENY_KEYS:
                f=fact({'field':k,'value':v},f'extra/{k}',f'root-{ri}')
                if f:fs.append(f)
        deadlines=[f for f in fs if ('报名' in f['label'] or '申请' in f['label']) and ('截止' in f['label']) and not f['excluded']]
        unique={f['value'] for f in deadlines if f['value']}
        deadline=None
        if len(unique)==1 and deadlines and all(f['usage']['date_action'] for f in deadlines):
            candidate=exact_day(next(iter(unique)))
            exact_support=False
            for f in deadlines:
                for ref in f['evidence']:
                    if not ref['located']:continue
                    m=re.fullmatch(r'(?:报名|申请)截止(?:日期|时间)?[\s：:为]*([0-9]{4}[-年/][0-9]{1,2}[-月/][0-9]{1,2}日?)[。.\s]*',ref['quote'].strip())
                    if m and exact_day(m.group(1))==candidate:exact_support=True
            if candidate and exact_support:deadline=candidate
        if len(unique)>1:
            for f in deadlines:
                f['notes']=list(dict.fromkeys(f['notes']+['报名截止存在冲突，不生成截止提醒。']))
                f['usage']['date_action']=False
        # Reliable identity only from producer stable key or concrete notice URL.
        stable=r.get('source_record_key')
        if stable:identity_key=hash_json([source['id'],url,text(stable,256)])
        elif url and url.rstrip('/')!=source['url'].rstrip('/') and url_counts[url]==1:identity_key=hash_json([source['id'],url])
        else:identity_key=hash_json([source['id'],hashlib.sha256(files.get('opportunities.json',b'')).hexdigest(),ri])
        typ=category(r.get('opportunity_type') or r.get('type') or r.get('category'))
        item_notes=[]
        if deadlines and not deadline:item_notes.append('报名时间尚不能用于精确提醒。')
        if any(f['notes'] for f in fs) or any(f['notes'] for c in children for f in c['fields']):item_notes.append('部分内容附有材料备注。')
        opportunities.append({'identity_key':identity_key,'title':title,'type':typ,
         'issuer':text(r.get('publish_unit') or r.get('issuer') or source['name'],300),
         'source_name':source['name'],'official_url':url,'application_url':safe_url(r.get('application_url')),
         'region':text(r.get('region') or r.get('work_location') or '',300),
         'summary':text(r.get('summary') or '',2000),'fields':fs,'children':children,
         'notes':item_notes,'deadline':deadline,'deadline_precision':'day' if deadline else None,
         'eligibility':'UNCERTAIN','raw_type':text(r.get('opportunity_type') or r.get('type') or '',100),
         'qualification_coverage':text((r.get('metadata') if isinstance(r.get('metadata'),dict) else {}).get('qualification_coverage') or r.get('qualification_coverage') or '',32).upper(),
         'lifecycle_status':lifecycle_status(r.get('lifecycle_status'),r.get('opportunity_status'),r.get('status'))})
    unlocated=sum(1 for x in opportunities for f in x['fields'] if f['value'] and not f['quote_located'] and not f['excluded'])
    if unlocated:notes.append(f'本份返回有{unlocated}项共同内容尚未定位引用，原文与对应备注已保留。')
    if len(roots)>1000:blockers.append('本次返回超过1000个机会，请拆分后再收录。')
    if not opportunities and not blockers:blockers.append('未找到可安全呈现的机会对象。')
    return {'adapter_version':ADAPTER_VERSION,'opportunities':opportunities,'artifacts':artifacts,
            'excluded_objects':excluded_objects,'notes':list(dict.fromkeys(notes)), 'blockers':list(dict.fromkeys(blockers)),
            'can_approve':not blockers and bool(opportunities),'field_count':num_fields,
            'report':files.get('report.md',b'').decode('utf-8',errors='replace')[:200000]}


def public_content(item,package_notes):
    """Explicit allowlist. Internal report/identity/raw paths never enter public API."""
    out={k:item[k] for k in ['title','type','issuer','source_name','official_url','application_url','region','summary','deadline','deadline_precision','eligibility','raw_type']}
    out['qualification_coverage']=item.get('qualification_coverage','')
    out['lifecycle_status']=item.get('lifecycle_status','ACTIVE')
    def clean(f):
        return {k:f[k] for k in ['id','label','value','state','section','notes','evidence','quote_located','usage','target']}
    out['fields']=[clean(f) for f in item['fields'] if not f['excluded']]
    out['children']=[{**{k:c.get(k) for k in ['id','source_key','identity_source','source_path','name','kind','parent_id','code','application_url','official_url','region','summary','lifecycle_status']},'fields':[clean(f) for f in c['fields'] if not f['excluded']]} for c in item['children']]
    out['notes']=list(dict.fromkeys(package_notes+item['notes']))
    return out
