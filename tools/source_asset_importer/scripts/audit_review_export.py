"""Read-only audit of a research handoff ZIP; never calls a network or database.

Usage: python scripts/audit_review_export.py INPUT.zip OUTPUT.json
A matching digest proves bytes/lineage only, not official source authenticity.
"""
from __future__ import annotations
import collections
import hashlib
import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deepaha_importer.contract import canonical_json, digest
from deepaha_importer.research.ingest import safe_member


def audit(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > 10000 or sum(x.file_size for x in infos) > 650*1024*1024:
            raise ValueError('Archive budget exceeded')
        names = [x.filename for x in infos if not x.is_dir()]
        for name in names:
            safe_member(name)
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        bad = z.testzip()
        if bad:
            raise ValueError('CRC check failed')
        manifest=json.loads(z.read('Manifest.json'))
        a=json.loads(z.read('Audit.json'))
        d=json.loads(z.read('Decisions.json'))
        h=json.loads(z.read('ResearchHandoff.json'))
        feedback=json.loads(z.read('FeedbackDeclarations.json'))
        members=[]
        for f in manifest['files']:
            raw=z.read(f['path'])
            members.append({'path':f['path'],'size_bytes':len(raw),'sha256':digest(raw),
                            'matches':len(raw)==f['size_bytes'] and digest(raw)==f['sha256']})
        sources={g['id']:g for g in a['sources']}
        decisions=d['decisions']; counts=dict(collections.Counter(x['decision'] for x in decisions.values()))
        replay={}; errors=[]
        for i,e in enumerate(d['events'],1):
            if e['revision']!=i: errors.append('NON_CONTIGUOUS_EVENT_REVISION')
            if e['type'] in ('DECISION','UNDO'):
                if replay.get(e['source_id']) != e.get('before'):errors.append('BEFORE_VALUE_MISMATCH')
                if e.get('after') is None:replay.pop(e['source_id'],None)
                else:replay[e['source_id']]=e['after']
        proposals={x['review_source_id'] for x in h['staging_proposals']}
        proposed={k for k,v in decisions.items() if v['decision']=='PROPOSE_STAGING'}
        inventory=h['original_inventory']
        actual_id=digest(canonical_json({'originals':inventory,'analysis_sha256':digest(canonical_json(a)),
                                        'decisions':decisions,'revision':d['revision'],'events':d['events']}))
        last_reviewed=max(e['at'] for e in d['events']) if d['events'] else None
        result={'input_file':path.name,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'scope':'USER_PROVIDED_EXPORT_ONLY_NO_LIVE_SYSTEM_OR_CODEX_LOGS',
            'zip_crc':'PASS','manifest_entries':members,
            'manifest_covers_every_non_manifest_file':set(f['path'] for f in manifest['files'])==set(names)-{'Manifest.json'},
            'bundle_id_matches':actual_id==h['bundle_id']==manifest['bundle_id'],
            'summary':a['summary'],'decision_counts':counts,'review_revision':d['revision'],
            'event_count':len(d['events']),'event_types':dict(collections.Counter(e['type'] for e in d['events'])),
            'event_replay_matches':not errors and replay==decisions and len(d['events'])==d['revision'],
            'event_errors':errors,'decisions_cover_all_sources':set(decisions)==set(sources),
            'proposals_match_decisions':proposals==proposed and len(proposals)==len(h['staging_proposals']),
            'blocked_sources_proposed':sum(sources[k]['blocking'] for k in proposed),
            'proposed_with_remaining_issues':sum(bool(sources[k]['issue_codes']) for k in proposed),
            'proposed_with_unacknowledged_issues':sum(bool(sources[k]['review_needed']) and not decisions[k]['acknowledged_issues'] for k in proposed),
            'issue_codes':dict(collections.Counter(i['code'] for i in a['issues'])),
            'deferred':[{'source_name':sources[k]['name'],'reason':v['reason']} for k,v in decisions.items() if v['decision']=='DEFER'],
            'handoff_status':{k:h[k] for k in ('schema_version','submission_status','delivery_mode','readiness','integration_status')},
            'no_system_source_ids':all(x['system_source_id'] is None for x in h['staging_proposals']),
            'no_collection_enabled':all(x['collection_enabled'] is None for x in h['staging_proposals']),
            'feedback_files':len(feedback),'timestamp_check':{'created_at':h['created_at'],'analyzed_at':a['analyzed_at'],
                'last_reviewed_at':last_reviewed,'created_at_before_last_review':bool(last_reviewed and h['created_at']<last_reviewed)},
            'limitations':['The package does not contain the failing Codex process log.',
                'An actor string and a review reason do not prove authenticated server-side approval.',
                'This audit does not query DeepAha production or start WMA.',
                'Matching hashes do not verify the semantic correctness of source research.']}
        return result

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('Usage: audit_review_export.py INPUT.zip OUTPUT.json')
    result=audit(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('bundle_id_matches','event_replay_matches','decision_counts','timestamp_check')},ensure_ascii=False,indent=2))
