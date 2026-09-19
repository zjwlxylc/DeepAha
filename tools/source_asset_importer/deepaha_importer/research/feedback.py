"""Offline feedback inspection. A file cannot authenticate its own issuer."""
from __future__ import annotations
import re
from datetime import datetime
from ..contract import parse_json,digest
from ..errors import ImporterError

EVENT_TYPES={'CANDIDATE_RECEIVED','CANDIDATE_REJECTED','SOURCE_APPROVED','SOURCE_SUSPENDED',
             'PRODUCTION_RUN_COMPLETED','PRODUCTION_RUN_FAILED','BRIEF_REVIEWED','SOURCE_MERGED'}

def inspect_feedback(raw,expected_bundle_ids=()):
    value=parse_json(raw,8*1024*1024)
    if not isinstance(value,dict) or value.get('schema_version')!='deepaha.scout-feedback.v1':
        raise ImporterError('FEEDBACK_SCHEMA','请提供 deepaha.scout-feedback.v1 系统反馈文件；旧回执请使用兼容窗口。')
    required={'issuer','instance_id','environment','feedback_id','bundle_id','observed_at','events'}
    if required-set(value):raise ImporterError('FEEDBACK_FIELDS','反馈缺少发行系统、实例、环境、包标识、时间或事件。')
    for key in ('issuer','instance_id','feedback_id'):
        if not isinstance(value[key],str) or not 0<len(value[key])<=240:raise ImporterError('FEEDBACK_FIELDS','反馈身份字段无效。')
    if value['environment'] not in {'DEMO','TEST','STAGING','PRODUCTION'}:raise ImporterError('FEEDBACK_ENV','反馈环境无效。')
    if not isinstance(value['bundle_id'],str) or not re.fullmatch('[0-9a-f]{64}',value['bundle_id']):raise ImporterError('FEEDBACK_BUNDLE','反馈包标识无效。')
    try:
        stamp=datetime.fromisoformat(value['observed_at'].replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError()
    except (ValueError,AttributeError,TypeError):raise ImporterError('FEEDBACK_TIME','反馈时间须为含时区的ISO时间。')
    events=value['events']
    if not isinstance(events,list) or len(events)>10000:raise ImporterError('FEEDBACK_EVENTS','反馈事件必须是有界数组。')
    ids=set()
    for e in events:
        if not isinstance(e,dict) or e.get('type') not in EVENT_TYPES or not isinstance(e.get('event_id'),str) or not 1<=len(e.get('event_id','').strip())<=240:raise ImporterError('FEEDBACK_EVENTS','事件类型或事件标识无效。')
        if e['event_id'] in ids:raise ImporterError('FEEDBACK_DUPLICATE','同一反馈内的事件标识重复。')
        ids.add(e['event_id'])
        if not isinstance(e.get('candidate_ref'),str) or not 1<=len(e['candidate_ref'].strip())<=800:
            raise ImporterError('FEEDBACK_EVENTS','事件缺少合法候选引用。')
        try:
            at=datetime.fromisoformat(e['occurred_at'].replace('Z','+00:00'))
            if at.tzinfo is None:raise ValueError()
        except (KeyError,ValueError,AttributeError,TypeError):raise ImporterError('FEEDBACK_TIME','每个事件时间须为含时区的ISO时间。')
        if e['type'] in {'SOURCE_APPROVED','SOURCE_SUSPENDED','SOURCE_MERGED'} and not e.get('system_source_id'):
            raise ImporterError('FEEDBACK_EVENTS','来源状态事件需要系统生成的来源ID。')
    known=value['bundle_id'] in expected_bundle_ids
    return {'sha256':digest(raw),'payload':value,
            'verification':{'structure':'PASS','bundle_binding':'MATCH' if known else 'NOT_MATCHED',
                            'authenticity':'UNVERIFIED','applied_to_official_state':False,
                            'message':'结构检查通过，不代表来自真实DeepAha。需由原系统查询或可信签名验证；本工具不将文件自报升级为正式状态。'}}
