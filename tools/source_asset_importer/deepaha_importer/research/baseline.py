"""Create a new operational boundary without falsifying historical completeness."""
from __future__ import annotations
import copy
from datetime import datetime,timezone
from pathlib import Path
from ..contract import parse_json,digest,canonical_json
from ..errors import ImporterError
from .ingest import _read_file

def _state(path):
    path=Path(path);raw=_read_file(path,8*1024*1024);data=parse_json(raw)
    if not isinstance(data,dict) or not isinstance(data.get('run_key'),str):
        raise ImporterError('INVALID_STATE','状态文件缺少批次标识。')
    return {'path':path.name,'sha256':digest(raw),'size_bytes':len(raw),'data':data}

def verify_state_chain(paths,external_parent=None):
    nodes=[_state(p) for p in paths];lookup={x['data']['run_key']:x for x in nodes}
    if len(lookup)!=len(nodes):raise ImporterError('STATE_ID_CONFLICT','状态链中批次标识重复。')
    if external_parent:
        ext=_state(external_parent);lookup[ext['data']['run_key']]=ext
    links=[]
    for node in nodes:
        ref=node['data'].get('parent_state_ref');ref=ref if isinstance(ref,dict) else {}
        parent=lookup.get(ref.get('run_key'))
        ok=bool(parent) and ref.get('sha256')==parent['sha256'] and ref.get('size_bytes')==parent['size_bytes']
        links.append({'run_key':node['data']['run_key'],'parent_run_key':ref.get('run_key'),'status':'PASS' if ok else 'FAIL',
                      'state_sha256':node['sha256'],'parent_sha256_actual':parent['sha256'] if parent else None})
    # A cycle is invalid even if each supplied byte declaration happens to match.
    for key in lookup:
        visited=set();cursor=key
        while cursor in lookup:
            if cursor in visited:raise ImporterError('STATE_CYCLE','状态引用中存在循环。')
            visited.add(cursor);ref=lookup[cursor]['data'].get('parent_state_ref',{})
            cursor=ref.get('run_key') if isinstance(ref,dict) else None
    return {'status':'PASS' if nodes and all(x['status']=='PASS' for x in links) else 'FAIL',
            'checked_links':len(links),'links':links,'scope':'PROVIDED_STATE_FILES_ONLY',
            'proves':'文件父子哈希与大小，不证明研究过程、事实准确性或全球历史完整。'}

def verify_archive_manifest(manifest_path,files_directory):
    manifest=parse_json(_read_file(Path(manifest_path),8*1024*1024));root=Path(files_directory);checks=[]
    for run in manifest.get('runs',[]):
        for role in ('review','handoff','state'):
            rec=run.get(role,{});name=rec.get('filename','')
            if not name or Path(name).name!=name:raise ImporterError('UNSAFE_MANIFEST','归档清单含非单文件名。')
            path=root/name
            if path.is_file():
                raw=_read_file(path,8*1024*1024);ok=digest(raw)==rec.get('sha256') and len(raw)==rec.get('size_bytes')
            else:ok=False
            checks.append({'run_key':run.get('run_key'),'role':role,'filename':name,'status':'PASS' if ok else 'FAIL'})
    return {'status':'PASS' if checks and all(x['status']=='PASS' for x in checks) else 'FAIL','checked_files':len(checks),'checks':checks,
            'meaning':'本地可读字节与已给归档清单核对；不是本次重新下载全部历史Library原件。'}

def create_controlled_baseline(selected,paths,*,authorizing_user,external_parent=None):
    if not isinstance(authorizing_user,str) or not authorizing_user.strip():raise ImporterError('AUTHORIZATION_REQUIRED','建立受控基线需要项目所有者授权。')
    selected_node=_state(selected);chain=verify_state_chain(paths,external_parent)
    if chain['status']!='PASS':raise ImporterError('STATE_CHAIN_FAILED','状态父子哈希未全部通过，不能固化为受控基线。')
    if selected_node['data']['run_key'] not in {x['run_key'] for x in chain['links']}:
        raise ImporterError('STATE_NOT_IN_CHAIN','所选基线不在已核验链中。')
    selected_link=next(x for x in chain['links'] if x['run_key']==selected_node['data']['run_key'])
    if selected_link['state_sha256']!=selected_node['sha256']:
        raise ImporterError('STATE_BYTES_NOT_VERIFIED','所选状态与已核验链同名但内容不同，不能固化。')
    base=copy.deepcopy(selected_node['data']);now=datetime.now(timezone.utc).isoformat()
    bid='CB-'+selected_node['sha256'][:16]
    gaps=[]
    for value in base.get('missing_history',[]):
        gaps.append({'gap_id':'MG-'+digest(canonical_json(value))[:16],'original_description':value,
                     'status':'PERMANENT_MIGRATION_RECORD','resolution':'NOT_RECOVERED_AT_CUTOFF',
                     'future_policy':'保留此记录；后续找到原件以新的补证事件关联，不删除或改写旧结论。'})
    base['controlled_baseline']={
        'schema_version':'deepaha.scout-controlled-baseline.v1','baseline_id':bid,
        'established_at':now,'authorization':{'actor':authorizing_user.strip(),'basis':'用户明确要求选择新受控基线并永久记录旧缺口'},
        'operational_status':'READY','historical_completeness':'PARTIAL_WITH_PERMANENT_MIGRATION_GAPS',
        'production_state':'NOT_OBSERVED','selected_checkpoint':{k:v for k,v in selected_node.items() if k!='data'},
        'selected_run_key':selected_node['data']['run_key'],'chain_verification':chain,'permanent_migration_gaps':gaps,
        'scope':'外部Scout研究工作集，不是DeepAha正式Source Registry或模型真实执行凭证。',
        'continuation_policy':{
            'preserve_source_keys_and_first_seen':True,'keep_all_original_versions':True,
            'do_not_repeat_legacy_gap_recovery_each_run':True,'unseen_receipts_not_assumed_failed_or_successful':True,
            'new_count_scope':'相对于本受控基线及之后可核验增量；不是全系统首次发现。',
            'post_baseline_missing_delta':'后续缺失属于新运行故障，必须阻断完整继承，不能归入旧迁移豁免。',
            'feedback':'仅凭DeepAha真实导出回执更新系统状态；本地审查意见单列。'},
        'inherited_metadata_notice':'旧inheritance_verification、brief_history_status等原字段保留为历史申报；本次核验以controlled_baseline为准。'}
    return base
