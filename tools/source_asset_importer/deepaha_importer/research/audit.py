"""Audit at file, run, candidate-version, endpoint and evidence grains.

A projection is not a verified fact. No automatic cross-producer identity merge.
"""
from __future__ import annotations
import collections
import itertools
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from ..contract import Package, canonical_json, digest
from ..errors import ImporterError
from .normalize import field, items, reference, score_check, seed_urls, name_key, semantic_hash, evidence_references


def _at(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.timestamp() if d.tzinfo else float('-inf')
    except (ValueError,TypeError,OverflowError): return float('-inf')


def _flatten_graph(value):
    if isinstance(value,list):return [x for x in value if isinstance(x,dict)]
    if isinstance(value,dict):
        if any(k in value for k in ('from_ref','source','from','to_ref')):return [value]
        return [r for v in value.values() for r in _flatten_graph(v)]
    return []


def analyze(inputs):
    issues=[]; groups={}; evidence=[]; briefs=[]; graphs=[]; batches=[]
    # Duplicate files/runs are identified but every original is retained.
    seen_run_bytes=set(); run_hashes=collections.defaultdict(set); documents=[]
    for doc in inputs.handoffs:
        n,run=doc['namespace'],doc['run_key'];h=doc['blob'].sha256
        run_hashes[(n,run)].add(h)
        if (n,run,h) in seen_run_bytes:continue
        seen_run_bytes.add((n,run,h));documents.append(doc)
    run_conflicts={key for key,value in run_hashes.items() if len(value)>1}
    evidence_index=collections.defaultdict(list); source_keys=set()
    for doc in documents:
        n,run,data=doc['namespace'],doc['run_key'],doc['data']; origin=doc['blob'].metadata()
        meta=data['run_metadata']; compatible=True; legacy_error=None
        try:Package.from_bytes(doc['blob'].data)
        except ImporterError as exc:compatible=False;legacy_error={'code':exc.code,'message':exc.message}
        batches.append({'namespace':n,'run_key':run,'origin':origin,'generated_at':meta.get('generated_at'),
                        'state_inheritance_claim':meta.get('state_inheritance'),'source_versions':len(data['source_candidates']),
                        'legacy_import_profile_compatible':compatible,'legacy_import_error':legacy_error,
                        'submission_status':'NOT_SUBMITTED','producer_identity_basis':'EXPLICIT_OR_FILENAME_CONVENTION_NOT_MODEL_ATTESTATION'})
        for i,r in enumerate(data.get('research_evidence',[])):
            if not isinstance(r,dict):continue
            k=field(r,'evidence_key','evidence_id') or f'unkeyed-evidence-{i}'
            row={'namespace':n,'run_key':run,'key':str(k),'payload':r,'origin':origin,'pointer':f'/research_evidence/{i}'}
            evidence.append(row);evidence_index[(n,str(k))].append(row)
        for i,r in enumerate(data.get('agent_acquisition_briefs',[])):
            if not isinstance(r,dict):continue
            briefs.append({'namespace':n,'run_key':run,'key':field(r,'brief_key') or f'brief-{i}',
                           'source_ref':reference(field(r,'source_ref')),'payload':r,'origin':origin,'pointer':f'/agent_acquisition_briefs/{i}'})
        for i,r in enumerate(_flatten_graph(data.get('source_graph_delta',[]))):
            graphs.append({'namespace':n,'run_key':run,'payload':r,'origin':origin,'pointer':f'/source_graph_delta/{i}'})
        for i,r in enumerate(data['source_candidates']):
            if not isinstance(r,dict):
                issues.append({'code':'INVALID_SOURCE_RECORD','severity':'BLOCKER','locator':origin['locator'],'pointer':f'/source_candidates/{i}'});continue
            key=field(r,'candidate_key')
            if not isinstance(key,str) or not key:
                key='missing-key-'+digest(canonical_json(r))[:16]
            source_keys.add((n,key)); identity=n+'::'+key; gid='src-'+digest(identity.encode())[:20]
            group=groups.setdefault(identity,{'id':gid,'namespace':n,'candidate_key':key,'versions':[]})
            group['versions'].append({'run_key':run,'generated_at':meta.get('generated_at'), 'payload':r,
                                     'origin':origin,'pointer':f'/source_candidates/{i}', 'semantic_hash':semantic_hash(r)})
    # State snapshots provide reference context, not additional handoff events.
    context_evidence=set(); context_sources=set()
    for state in inputs.states:
        n=state['namespace'];data=state['data']
        for r in data.get('research_evidence',[]) if isinstance(data.get('research_evidence',[]),list) else []:
            if isinstance(r,dict) and field(r,'evidence_key'):context_evidence.add((n,str(field(r,'evidence_key'))))
        for r in field(data,'source_candidates','candidates',default=[]) if isinstance(field(data,'source_candidates','candidates',default=[]),list) else []:
            if isinstance(r,dict) and field(r,'candidate_key'):context_sources.add((n,str(field(r,'candidate_key'))))
    group_by_id={g['id']:g for g in groups.values()}
    def issue(code,severity,group=None,**extra):
        row={'code':code,'severity':severity,**extra}
        if group is not None:row['source_id']=group['id']
        issues.append(row);return row
    for identity,g in groups.items():
        g['versions'].sort(key=lambda v:(_at(v['generated_at']),v['run_key'],v['origin']['sha256']))
        current=g['versions'][-1];r=current['payload'];n=g['namespace']
        raw_seed=field(r,'recommended_seed','seed_url','url');urls=seed_urls(raw_seed)
        g.update({'name':field(r,'source_name',default=g['candidate_key']), 'institution':field(r,'institution',default='未说明'),
                  'seed_original':raw_seed,'seed_urls':urls,'roles':items(field(r,'source_role')),
                  'opportunity_types':items(field(r,'opportunity_types')),'demand_themes':items(field(r,'demand_themes')),
                  'recommendation':field(r,'recommendation',default='未建议'),'recon_status':field(r,'recon_status',default='未知'),
                  'authority_claim':field(r,'authority_assessment'),'authority_validation':'NOT_INDEPENDENTLY_VERIFIED',
                  'latest_projection_basis':'DECLARED_TIMESTAMP_THEN_RUN_KEY_NOT_TRUTH_PRECEDENCE',
                  'current':current,'score':score_check(r),'system_source_id':None,'system_revision':None,
                  'collection_enabled':None,'decision':'PENDING','repeat_versions':len(g['versions'])-1})
        g['brief_versions']=[b for b in briefs if b['namespace']==n and b['source_ref']==g['candidate_key']]
        seen_refs=[]
        for v in g['versions']:
            rec=v['payload'];sc=score_check(rec)
            if sc['arithmetic_mismatch']:issue('SCORE_ARITHMETIC_MISMATCH','REVIEW',g,run_key=v['run_key'],detail=sc)
            if (n,v['run_key']) in run_conflicts:issue('RUN_CONTENT_CONFLICT','BLOCKER',g,run_key=v['run_key'])
            if not field(rec,'candidate_key'):issue('MISSING_CANDIDATE_KEY','BLOCKER',g,run_key=v['run_key'])
            known={key for ns,key in evidence_index if ns==n}|{key for ns,key in context_evidence if ns==n}
            for value in items(field(rec,'evidence_refs')):
                refs=evidence_references(value,known)
                if not refs:issue('INVALID_EVIDENCE_REFERENCE','REVIEW',g,run_key=v['run_key']);continue
                if refs != [reference(value)]:
                    issue('REFERENCE_TEXT_NORMALIZATION_PROPOSAL','INFO',g,run_key=v['run_key'],raw=value,resolved_refs=refs)
                for ref in refs:
                    if ref not in seen_refs:seen_refs.append(ref)
                    if ref not in known:
                        issue('MISSING_EVIDENCE_REFERENCE','REVIEW',g,run_key=v['run_key'],reference=ref,scope='ALL_SELECTED_HANDOFFS_AND_STATES')
        known={key for ns,key in evidence_index if ns==n}|{key for ns,key in context_evidence if ns==n}
        for b in g['brief_versions']:
            for value in items(field(b['payload'],'recon_evidence')):
                refs=evidence_references(value,known)
                if refs and refs != [reference(value)]:
                    issue('REFERENCE_TEXT_NORMALIZATION_PROPOSAL','INFO',g,run_key=b['run_key'],raw=value,resolved_refs=refs)
                for ref in refs:
                    if ref not in seen_refs:seen_refs.append(ref)
                    if ref not in known:
                        issue('MISSING_BRIEF_EVIDENCE_REFERENCE','REVIEW',g,run_key=b['run_key'],reference=ref)
        g['evidence_versions']=[e for ref in seen_refs for e in evidence_index.get((n,ref),[])]
        if not urls:issue('INVALID_SEED','BLOCKER',g,run_key=current['run_key'],detail='没有可安全识别的公开HTTP(S)入口。')
        elif len(urls)>1:issue('MULTIPLE_SEEDS','REVIEW',g,run_key=current['run_key'],detail='需选择主入口；其他URL保留为待审核关联入口。')
        elif isinstance(raw_seed,str) and urls[0]!=raw_seed:issue('SEED_NORMALIZATION_PROPOSAL','INFO',g,raw=raw_seed,proposed=urls[0])
        endpoint_sets={tuple(seed_urls(field(v['payload'],'recommended_seed','seed_url','url'))) for v in g['versions']}
        if len(endpoint_sets)>1:issue('SEED_CHANGED_ACROSS_VERSIONS','REVIEW',g,detail=[list(s) for s in sorted(endpoint_sets)])
        if not g['brief_versions']:issue('BRIEF_NOT_IN_SELECTED_HANDOFFS','REVIEW',g)
        for key in ('source_name','institution','source_role','recommendation','recon_status'):
            vals=[]
            for v in g['versions']:
                value=field(v['payload'],key)
                if value not in vals:vals.append(value)
            if len(vals)>1:
                g.setdefault('field_history',{})[key]=vals
        # Do not let externally supplied system IDs turn into confirmed mappings.
        claims=[field(v['payload'],'system_source_id') for v in g['versions'] if field(v['payload'],'system_source_id')]
        if claims:g['unverified_system_id_claims']=list(dict.fromkeys(claims));issue('SYSTEM_MAPPING_UNVERIFIED','REVIEW',g)
        originals=[v['payload'].get('first_seen_at') for v in g['versions']]
        g['first_seen_claims']=list(dict.fromkeys(str(x) for x in originals if x is not None))
        if len(g['first_seen_claims'])>1:issue('FIRST_SEEN_CHANGED','REVIEW',g,detail=g['first_seen_claims'])
    for b in briefs:
        if (b['namespace'],b['source_ref']) not in source_keys|context_sources:
            issue('BRIEF_SOURCE_OUTSIDE_SELECTION','REVIEW',reference=b['source_ref'],run_key=b['run_key'],namespace=b['namespace'])
    graph_refs=[]
    for graph in graphs:
        rec=graph['payload'];n=graph['namespace']
        for key in ('from_ref','to_ref','source','target','from','to'):
            ref=reference(rec.get(key))
            if not ref:continue
            if (n,ref) not in source_keys|context_sources:
                # Networks/demand/archetypes may intentionally be external nodes.
                graph_refs.append({'namespace':n,'run_key':graph['run_key'],'reference':ref,
                                   'status':'EXTERNAL_OR_UNRESOLVED_NODE_NOT_AUTO_SOURCE','pointer':graph['pointer']})
    relations=[];byurl=collections.defaultdict(list)
    for g in groups.values():
        for url in g['seed_urls']:byurl[url].append(g)
    seen_pairs=set()
    for url,gs in byurl.items():
        for a,b in itertools.combinations(gs,2):
            pair=tuple(sorted((a['id'],b['id'])));seen_pairs.add(pair)
            relations.append({'kind':'SAME_ENDPOINT','left':a['id'],'right':b['id'],'url':url,
                              'recommendation':'REVIEW_SOURCE_IDENTITY','reason':'公开入口规范键相同；不等于同一机构或相同权限。',
                              'cross_producer':a['namespace']!=b['namespace'],'auto_merged':False})
    gs=list(groups.values())
    for a,b in itertools.combinations(gs,2):
        if tuple(sorted((a['id'],b['id']))) in seen_pairs:continue
        hosts_a={urlsplit(u).hostname for u in a['seed_urls']};hosts_b={urlsplit(u).hostname for u in b['seed_urls']}
        same_name=name_key(a['name']) and name_key(a['name'])==name_key(b['name'])
        if same_name or hosts_a & hosts_b:
            relations.append({'kind':'SAME_NAME' if same_name else 'SAME_HOST_DIFFERENT_ENDPOINT',
                              'left':a['id'],'right':b['id'],'auto_merged':False,
                              'recommendation':'REVIEW_RELATION_KEEP_SEPARATE','reason':'相同名称或主机只构成关联线索，不自动合并不同栏目。',
                              'cross_producer':a['namespace']!=b['namespace']})
    # Actual byte checks of bundled samples. No PDF/Office interpretation here.
    sample_blobs=[b for b in inputs.files if not b.name.lower().endswith(('.json','.md','.txt','.csv'))]
    byhash=collections.defaultdict(list)
    for b in sample_blobs:byhash[b.sha256].append(b)
    attachment_refs=[];state_refs=[];claimed_hashes=set()
    all_hashes={b.sha256:b for b in inputs.files}
    for e in evidence:
        r=e['payload'];path=field(r,'local_path','local_file','file_path','relative_path')
        declared=field(r,'sha256','file_sha256'); hash_basis='FIELD'
        if not isinstance(declared,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',declared):
            # Observation text is a declaration, never proof by itself.
            found=re.findall(r'(?i)sha256\s*[=:：]\s*([0-9a-f]{64})',str(r))
            declared=found[0] if len(set(found))==1 else None;hash_basis='EXPLICIT_TEXT_DECLARATION' if declared else None
        if not path and not declared:continue
        declared=declared.lower() if declared else None
        url_claim=str(field(r,'url','public_url',default='') or '')
        if url_claim.startswith(('library:', 'sandbox:')) or str(path or '').lower().endswith('_state.json'):
            state_refs.append({'namespace':e['namespace'],'run_key':e['run_key'],'evidence_key':e['key'],
                               'declared_sha256':declared,'url':url_claim,'status':'BYTE_MATCH' if declared in all_hashes else 'NOT_IN_SELECTED_FILES',
                               'meaning':'状态/归档引用，不是官方附件或新的公网研究证据。'})
            continue
        matches=byhash.get(declared,[]) if declared else []
        stated_bytes=field(r,'size_bytes','bytes','byte_size')
        size_ok=stated_bytes is None or (type(stated_bytes) is int and matches and len(matches[0].data)==stated_bytes)
        if matches:
            claimed_hashes.add(declared);status='HASH_AND_SIZE_MATCH' if size_ok else 'SIZE_CLAIM_MISMATCH'
        elif declared:status='DECLARED_HASH_NOT_IN_SELECTED_PACKAGE'
        else:status='PATH_ONLY_UNVERIFIED'
        mapped=[b.metadata() for b in matches]
        normalized_path=str(path or '').replace('\\','/')
        path_match=any(b.name==normalized_path or b.name.endswith('/'+normalized_path) for b in matches)
        row={'namespace':e['namespace'],'run_key':e['run_key'],'evidence_key':e['key'],
             'declared_path':path,'declared_sha256':declared,'hash_basis':hash_basis,'declared_size':stated_bytes,
             'status':status,'matched_files':mapped,'path_mapping_needed':bool(matches) and not path_match,
             'public_url_claim':field(r,'url','public_url'),'official_origin_verified':False,
             'semantic_reading_performed':False}
        attachment_refs.append(row)
        if status!='HASH_AND_SIZE_MATCH':
            affected=[g for g in groups.values() if g['namespace']==e['namespace'] and any(x['key']==e['key'] for x in g['evidence_versions'])]
            if affected:
                for g in affected:issue('ATTACHMENT_'+status,'REVIEW',g,run_key=e['run_key'],reference=e['key'])
            else:issue('ATTACHMENT_'+status,'REVIEW',run_key=e['run_key'],reference=e['key'])
    attachment_files=[]
    for b in sample_blobs:
        head=b.data[:16];kind=('PDF' if head.startswith(b'%PDF') else 'ZIP_OR_OOXML' if head.startswith(b'PK') else
                            'OLE_COMPOUND' if head.startswith(bytes.fromhex('d0cf11e0a1b11ae1')) else 'OTHER')
        attachment_files.append(b.metadata()|{'magic_family':kind,'has_matching_hash_declaration':b.sha256 in claimed_hashes,
                                             'official_origin_verified':False,'semantic_reading_performed':False})
    for g in groups.values():
        relevant=[x for x in issues if x.get('source_id')==g['id']]
        g['issue_codes']=sorted({x['code'] for x in relevant});g['blocking']=any(x['severity']=='BLOCKER' for x in relevant)
        g['review_needed']=any(x['severity'] in {'REVIEW','BLOCKER'} for x in relevant) or any(g['id'] in (x['left'],x['right']) for x in relations)
    public_urls={u for e in evidence for u in seed_urls(field(e['payload'],'url','public_url'))}
    namespace_stats={}
    for n in sorted({x['namespace'] for x in batches}):
        ng=[g for g in groups.values() if g['namespace']==n]
        namespace_stats[n]={'batches':len([b for b in batches if b['namespace']==n]),'source_versions':sum(len(g['versions']) for g in ng),
                            'candidate_groups':len(ng),'brief_versions':sum(b['namespace']==n for b in briefs),
                            'evidence_records':sum(e['namespace']==n for e in evidence)}
    timeline_issues=[]
    for doc in documents:
        meta=doc['data']['run_metadata']
        if meta.get('started_at') and meta.get('started_at')==meta.get('recon_completed_at'):
            timeline_issues.append({'run_key':doc['run_key'],'code':'ZERO_DECLARED_RESEARCH_DURATION',
                                    'meaning':'文件中的开始与完成时间相同；不能据此证明独立连续联网执行。'})
    return {'schema_version':'deepaha.research-review.v1','tool_version':'0.3.1',
            'analyzed_at':datetime.now(timezone.utc).isoformat(),'scope':'SELECTED_ORIGINAL_FILES_ONLY',
            'database_submission':'NOT_ATTEMPTED','official_sources_created':0,'official_facts_approved':0,
            'summary':{'input_originals':len(inputs.originals),'files':len(inputs.files),'batches':len(batches),
                       'duplicate_handoff_files':len(inputs.handoffs)-len(documents),'run_conflicts':len(run_conflicts),
                       'source_versions':sum(len(g['versions']) for g in groups.values()),'candidate_groups':len(groups),
                       'repeated_identity_versions':sum(len(g['versions'])-1 for g in groups.values()),
                       'brief_versions':len(briefs),'evidence_records':len(evidence),'public_evidence_urls':len(public_urls),
                       'attachment_files':len(attachment_files),'attachment_references':len(attachment_refs),
                       'legacy_profile_compatible_batches':sum(b['legacy_import_profile_compatible'] for b in batches),
                       'same_endpoint_pairs':sum(x['kind']=='SAME_ENDPOINT' for x in relations),
                       'blocked_sources':sum(g['blocking'] for g in groups.values()),'issue_count':len(issues),
                       'timeline_anomalies':len(timeline_issues)},
            'namespace_summary':namespace_stats,'sources':sorted(groups.values(),key=lambda g:(not g['blocking'],not g['review_needed'],g['namespace'],str(g['name']))),
            'batches':batches,'relations':relations,'issues':issues,'timeline_issues':timeline_issues,
            'briefs':briefs,'evidence':evidence,'graphs':graphs,'external_graph_nodes':graph_refs,
            'attachments':attachment_files,'attachment_reconciliation':attachment_refs,'state_reference_reconciliation':state_refs,
            'inventory':[b.metadata() for b in inputs.files],'warnings':inputs.warnings,
            'retention':'全部输入原件、未映射字段、旧版本和研究关系保留在导出包originals中；投影不是原文替代品。',
            'limits':'仅离线结构/关联/字节审核，不证明网页当前可用、官方身份、30次真实执行或DeepAha已接纳。'}
