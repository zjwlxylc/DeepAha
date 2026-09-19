"""Research package intake → candidate observations → explicit Source binding.

No source approval, scheduling, network call or opportunity publication occurs
while accepting a package. All writes use the existing serialized transaction.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import select, func

from .adapter import hash_json, safe_url
from .auth import aware
from .errors import Problem
from .models import Source, SourceProfile, Meta, now, uid
from .scout_models import (ScoutBatch, ScoutRun, ScoutCandidate, ScoutObservation,
                           ScoutBinding, ScoutEvent, ScoutApproval, TaskSourceContext)
from .scout_package import FORMAT, RAW_FORMAT, MAX_UPLOAD, parse_package
from .storage import sha


def _string(value, name, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise Problem(name + '格式不正确')
    return value.strip()


def _page(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise Problem('分页参数不正确')


def _briefs(g):
    return [{'id':hash_json([b['namespace'], b['run_key'], b['key'], b['payload']]), **b}
            for b in g.get('brief_versions', [])]


class ScoutMixin:
    feedback_environment = 'STAGING'

    def _scout_init(self):
        with self.db.tx() as s:
            version=s.get(Meta,'scout_schema_version')
            if version and version.value!='1':
                raise Problem('来源资产结构版本不兼容',409)
            if not version:s.add(Meta(key='scout_schema_version',value='1'))
            for key in ('scout_epoch', 'instance_id'):
                if not s.get(Meta, key):
                    s.add(Meta(key=key, value=uid()))

    def _scout_batch(self, s, batch_id):
        b = s.get(ScoutBatch, batch_id)
        if not b:
            raise Problem('研究交接记录不存在', 404)
        if b.status=='DUPLICATE':
            original=s.get(ScoutBatch,b.projection.get('canonical_batch_id',''))
            if not original or original.status=='DUPLICATE':raise Problem('重复文件原始记录不可读取',409)
            return original
        return b

    def _scout_baseline(self, s, b):
        epoch = s.get(Meta, 'scout_epoch').value
        conflicts = set()
        seen = {}
        runs = []
        for run in b.projection.get('runs', []):
            k = (run['namespace'], run['run_key'])
            old = s.scalar(select(ScoutRun).where(ScoutRun.epoch == epoch,
                      ScoutRun.namespace == k[0], ScoutRun.run_key == k[1]))
            if (old and old.sha256 != run['sha256']) or (k in seen and seen[k] != run['sha256']):
                conflicts.add(k)
            seen[k] = run['sha256']
            runs.append([*k, old.sha256 if old else None])
        groups = b.projection.get('analysis', {}).get('sources', [])
        urls = {u for g in groups for u in g['seed_urls']}
        existing = []
        if urls:
            for src in s.scalars(select(Source).where(Source.canonical_url.in_(urls))):
                p = s.get(SourceProfile, src.source_id)
                existing.append({'id':str(src.source_id), 'name':src.authority_name, 'url':src.canonical_url,
                      'policy_version':p.policy_version if p else 0, 'tier':src.tier,
                      'allowed_hosts':p.allowed_hosts if p else [],
                      'enabled':bool(p and p.scheduling_enabled), 'active':src.active})
        fingerprint = hash_json({'package':b.package_sha256, 'projection':b.projection,
                       'runs':sorted(runs), 'existing':sorted(existing, key=lambda x:x['id'])})
        return fingerprint, conflicts, existing

    def _scout_view(self, s, b):
        fingerprint, conflicts, _ = self._scout_baseline(s, b)
        summary = b.projection.get('analysis', {}).get('summary', {})
        return {'id':b.id, 'filename':b.filename, 'package_sha256':b.package_sha256,
                'bundle_id':b.bundle_id, 'format':b.format, 'status':b.status,
                'created_at':aware(b.created_at).isoformat(), 'preview_hash':fingerprint,
                'summary':summary, 'readiness':b.projection.get('readiness'),
                'conflicting_runs':[{'namespace':n, 'run_key':r} for n,r in sorted(conflicts)],
                'warnings':b.projection.get('warnings', []), 'error':b.error,
                'suggested_ids':[g['id'] for g in b.projection.get('analysis',{}).get('sources',[]) if g.get('suggested')],
                'receipt':b.receipt, 'can_receive':b.status == 'PREPARED'}

    def scout_capabilities(self, *, actor):
        with self.db.tx(False) as s:
            self._account(s, actor, 'operator')
            return {'protocol':'deepaha.scout-intake.v1', 'formats':[FORMAT, RAW_FORMAT],
                'feedback_format':'deepaha.scout-feedback.v1', 'max_upload_bytes':MAX_UPLOAD,
                'instance_id':s.get(Meta, 'instance_id').value,
                'environment':self.feedback_environment,
                'automatic_source_approval':False, 'automatic_wma_dispatch':False,
                'legacy_import_profile_api':False, 'manual_upload':True}

    def scout_prepare(self, raw, filename, *, actor):
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_UPLOAD:
            raise Problem('请选择不超过100MiB的研究文件', 413, 'SCOUT_UPLOAD_LIMIT')
        filename = _string(filename, '文件名', 200)
        filename = Path(filename.replace('\\', '/')).name
        if not filename.lower().endswith(('.zip', '.json')):
            raise Problem('请选择研究交接ZIP或Handoff.json')
        with self.db.tx(False) as s:
            self._account(s, actor, 'operator')
        digest = sha(raw)
        manifest = self.store.save({'upload/' + filename:raw})
        with self.db.tx() as s:
            self._account(s, actor, 'operator')
            b = s.scalar(select(ScoutBatch).where(ScoutBatch.package_sha256 == digest))
            if b and b.status != 'PREPARING':
                return self._scout_view(s, self._scout_batch(s,b.id))
            if not b:
                b = ScoutBatch(package_sha256=digest, filename=filename, actor=actor, manifest=manifest)
                s.add(b); s.flush()
                self._audit(s, actor, 'SCOUT_UPLOAD', b.id, '保存外部研究原件；未登记来源')
            batch_id = b.id
        try:
            parsed = parse_package(raw, filename)
            manifest = self.store.save(parsed.pop('archive_files'))
        except Problem as exc:
            with self.db.tx() as s:
                b = self._scout_batch(s, batch_id)
                if b.status!='PREPARING':return self._scout_view(s,b)
                b.status = 'INVALID'; b.error = exc.message
                b.projection = {'error_code':exc.code}
                self._audit(s, actor, 'SCOUT_READ_FAILED', b.id, exc.code)
                return self._scout_view(s, b)
        with self.db.tx() as s:
            b = self._scout_batch(s, batch_id)
            if b.status != 'PREPARING':
                return self._scout_view(s,b)
            same=s.scalar(select(ScoutBatch).where(ScoutBatch.bundle_id==parsed['bundle_id'], ScoutBatch.id!=b.id, ScoutBatch.status.in_(['PREPARED','COMMITTED'])))
            if same:
                # The checked bundle ID commits original bytes, audit and decisions.
                # Different compression/root names preserve the same logical intake.
                b.status='DUPLICATE';b.format=parsed['format'];b.bundle_id=parsed['bundle_id'];b.manifest=manifest
                b.projection={'canonical_batch_id':same.id}
                self._audit(s,actor,'SCOUT_DUPLICATE',b.id,'相同交接内容；复用原批次 '+same.id)
                return self._scout_view(s,same)
            b.format = parsed['format']; b.bundle_id = parsed['bundle_id']
            b.manifest = manifest; b.projection = parsed; b.status = 'PREPARED'
            self._audit(s, actor, 'SCOUT_PREVIEW', b.id, '从原件重建候选与采集建议；未接收候选')
            return self._scout_view(s, b)

    def scout_batch(self, batch_id, *, actor):
        with self.db.tx(False) as s:
            self._account(s, actor, 'operator')
            return self._scout_view(s, self._scout_batch(s, batch_id))

    def scout_batches(self, *, actor, offset=0, limit=20):
        _page(offset, limit)
        with self.db.tx(False) as s:
            self._account(s, actor, 'operator')
            total = s.scalar(select(func.count()).select_from(ScoutBatch).where(ScoutBatch.status!='DUPLICATE'))
            rows = s.scalars(select(ScoutBatch).where(ScoutBatch.status!='DUPLICATE').order_by(ScoutBatch.created_at.desc(), ScoutBatch.id).offset(offset).limit(limit))
            return {'items':[{'id':b.id, 'filename':b.filename, 'status':b.status,
                'created_at':aware(b.created_at).isoformat(), 'summary':b.projection.get('analysis', {}).get('summary', {}),
                'receipt':b.receipt, 'error':b.error} for b in rows], 'total':total}

    def _scout_rows(self, s, b):
        _, conflicts, existing = self._scout_baseline(s, b)
        observed = {o.review_source_id:o for o in s.scalars(select(ScoutObservation).where(ScoutObservation.batch_id == b.id))}
        rows = []
        for g in b.projection.get('analysis', {}).get('sources', []):
            conflict = any((g['namespace'], v['run_key']) in conflicts for v in g['versions'])
            obs = observed.get(g['id'])
            binding = s.get(ScoutBinding, obs.candidate_id) if obs else None
            rows.append({'id':g['id'], 'name':g['name'], 'institution':g['institution'],
                'namespace':g['namespace'], 'candidate_key':g['candidate_key'], 'seed_urls':g['seed_urls'],
                'suggested':g['suggested'], 'external_decision':g['external_decision'],
                'blocking':g['blocking'] or conflict, 'conflict':conflict, 'issue_codes':g['issue_codes'],
                'version_count':len(g['versions']), 'brief_count':len(g['brief_versions']),
                'state':obs.state if obs else 'PENDING', 'observation_id':obs.id if obs else None,
                'system_source_id':str(binding.source_id) if binding else None,
                'binding_current':bool(binding and binding.observation_id == obs.id),
                'existing_sources':[x for x in existing if x['url'] in g['seed_urls']]})
        return rows

    def scout_items(self, batch_id, *, actor, q='', offset=0, limit=50):
        _page(offset, limit); q = _string(q, '搜索词', 300, True)
        with self.db.tx(False) as s:
            self._account(s, actor, 'operator'); b = self._scout_batch(s, batch_id)
            rows = self._scout_rows(s, b)
            if q:
                rows = [r for r in rows if q.casefold() in (str(r['name']) + r['candidate_key'] + ' '.join(r['seed_urls'])).casefold()]
            return {'items':rows[offset:offset+limit], 'total':len(rows), 'preview_hash':self._scout_baseline(s,b)[0]}

    def scout_candidate_detail(self, batch_id, review_source_id, *, actor):
        with self.db.tx(False) as s:
            self._account(s, actor, 'operator'); b = self._scout_batch(s, batch_id)
            g = next((g for g in b.projection.get('analysis', {}).get('sources', []) if g['id'] == review_source_id), None)
            if not g:
                raise Problem('研究候选不存在', 404)
            row = next(r for r in self._scout_rows(s,b) if r['id'] == review_source_id)
            obs = s.get(ScoutObservation, row['observation_id']) if row['observation_id'] else None
            binding = s.get(ScoutBinding, obs.candidate_id) if obs else None
            current_source = self._source(s, binding.source_id) if binding else None
            return {**row, 'projection':g, 'briefs':_briefs(g),
                'approval_version':hash_json([obs.id, obs.payload, obs.state]) if obs else None,
                'binding_version':binding.version if binding else 0, 'bound_source':current_source,
                'materials':[{'name':n, **m} for n,m in b.manifest.items() if n.startswith('materials/')],
                'issues':[i for i in b.projection['analysis']['issues'] if i.get('source_id') == g['id']]}

    def scout_file(self, batch_id, name, *, actor):
        with self.db.tx(False) as s:
            self._account(s, actor, 'operator'); b = self._scout_batch(s, batch_id)
            return self.store.one(b.manifest, name)

    def scout_commit(self, batch_id, preview_hash, selected_ids, request_key, *, actor):
        _string(preview_hash, '预览标识', 64); _string(request_key, '提交标识', 128)
        if not isinstance(selected_ids, list) or not all(isinstance(x,str) for x in selected_ids) or len(selected_ids) > 2000 or len(set(selected_ids)) != len(selected_ids):
            raise Problem('所选候选清单不正确')
        chosen = sorted(selected_ids)
        request_hash = hash_json([batch_id, preview_hash, chosen, actor])
        with self.db.tx() as s:
            self._account(s, actor, 'operator'); b = self._scout_batch(s, batch_id)
            if b.receipt:
                if b.receipt['request_hash'] != request_hash:
                    raise Problem('本批次已完成接收，不能覆盖已保存决定；请查看回执', 409, 'SCOUT_ALREADY_COMMITTED')
                return b.receipt
            if b.status != 'PREPARED':
                raise Problem('研究包尚未形成可接收内容', 409, 'SCOUT_NOT_PREPARED')
            expected, conflicts, _ = self._scout_baseline(s, b)
            if preview_hash != expected:
                raise Problem('候选或来源记录已有变化，请刷新后再接收', 409, 'SCOUT_STALE_PREVIEW')
            groups = b.projection['analysis']['sources']
            if set(chosen) - {g['id'] for g in groups}:
                raise Problem('提交包含本次预览之外的候选', 400, 'SCOUT_SELECTION_INVALID')
            # Byte-level integrity is checked again before committing any semantic record.
            for m in b.manifest.values():
                raw = self.store.backend.get_bytes(key=m['key'])
                if sha(raw) != m['sha256'] or len(raw) != m['size']:
                    raise Problem('已保存原件完整性不符', 409, 'SCOUT_STORED_BYTES_CHANGED')
            epoch = s.get(Meta, 'scout_epoch').value
            for run in b.projection['runs']:
                if (run['namespace'], run['run_key']) in conflicts:
                    continue
                old = s.scalar(select(ScoutRun).where(ScoutRun.epoch==epoch, ScoutRun.namespace==run['namespace'], ScoutRun.run_key==run['run_key']))
                if not old:
                    s.add(ScoutRun(epoch=epoch, namespace=run['namespace'], run_key=run['run_key'], sha256=run['sha256'], batch_id=b.id, payload=run['payload']))
                    s.flush()
            mapping = []
            transaction_id = uid(); stamp = now()
            for g in groups:
                c = s.scalar(select(ScoutCandidate).where(ScoutCandidate.epoch==epoch, ScoutCandidate.namespace==g['namespace'], ScoutCandidate.candidate_key==g['candidate_key']))
                if not c:
                    c = ScoutCandidate(epoch=epoch, namespace=g['namespace'], candidate_key=g['candidate_key'])
                    s.add(c); s.flush()
                conflict = any((g['namespace'], v['run_key']) in conflicts for v in g['versions'])
                state = 'CONFLICT' if g['id'] in chosen and conflict else ('RECEIVED' if g['id'] in chosen else 'NOT_SELECTED')
                o = ScoutObservation(batch_id=b.id, candidate_id=c.id, review_source_id=g['id'], payload=g, state=state, conflict=conflict)
                s.add(o); s.flush()
                entry = {'review_source_id':g['id'], 'candidate_ref':g['namespace']+'::'+g['candidate_key'],
                    'candidate_id':c.id, 'candidate_revision_id':o.id, 'state':state, 'system_source_id':None,
                    'reason':'同一研究批次存在不同原件，未覆盖既有记录' if conflict else None}
                mapping.append(entry)
                if g['id'] in chosen:
                    typ = 'CANDIDATE_REJECTED' if conflict else 'CANDIDATE_RECEIVED'
                    s.add(ScoutEvent(batch_id=b.id, candidate_id=c.id, type=typ, created_at=stamp,
                        payload={**entry, 'transaction_id':transaction_id, 'source_approved':False, 'wma_started':False}))
            b.status = 'COMMITTED'
            b.receipt = {'schema_version':'deepaha.scout-intake.receipt.v1', 'transaction_id':transaction_id,
               'batch_id':b.id, 'bundle_id':b.bundle_id, 'package_sha256':b.package_sha256,
               'instance_id':s.get(Meta,'instance_id').value, 'environment':self.feedback_environment,
               'received_at':stamp.isoformat(), 'actor':actor, 'request_key':request_key, 'request_hash':request_hash,
               'candidates':mapping, 'received':sum(x['state']=='RECEIVED' for x in mapping),
               'conflicts':sum(x['state']=='CONFLICT' for x in mapping), 'not_selected':sum(x['state']=='NOT_SELECTED' for x in mapping),
               'sources_created':0, 'tasks_created':0, 'opportunities_created':0}
            self._audit(s, actor, 'SCOUT_RECEIVE', b.id, f"接收 {b.receipt['received']} 个候选；未登记来源、未创建调查")
        # Read a committed receipt in a fresh transaction, not an optimistic response.
        return self.scout_receipt(batch_id, actor=actor)

    def scout_receipt(self, batch_id, *, actor):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator'); b=self._scout_batch(s,batch_id)
            if not b.receipt:
                raise Problem('本批研究尚未接收，没有系统接收回执',409,'SCOUT_NO_RECEIPT')
            return b.receipt

    def scout_approve(self, observation_id, *, actor, approval_version, binding_version, name, url,
                      tier, reason, request_key, brief_id=None, allowed_hosts=None, enabled=False,
                      existing_source_id=None, expected_policy_version=None):
        _string(name,'来源名称',300); _string(reason,'批准原因',1000); _string(request_key,'请求标识',128)
        if type(enabled) is not bool or type(binding_version) is not int:
            raise Problem('批准选项格式不正确')
        if tier not in ('OFFICIAL_PRIMARY','OFFICIAL_AGGREGATOR','TRUSTED_SECONDARY','COMMUNITY_SIGNAL'):
            raise Problem('来源角色不正确')
        url = safe_url(url)
        if not url:
            raise Problem('所选入口不是有效的公开HTTP(S)网址')
        allowed_hosts = allowed_hosts or []
        if not isinstance(allowed_hosts,list) or len(allowed_hosts)>20 or not all(isinstance(h,str) for h in allowed_hosts):
            raise Problem('允许域名清单不正确')
        hosts=list(dict.fromkeys([urlsplit(url).hostname]+allowed_hosts))
        for h in hosts:
            candidate=safe_url('https://'+h)
            if not candidate or urlsplit(candidate).hostname!=h or urlsplit(candidate).path not in ('','/'):
                raise Problem('允许域名不正确')
        fingerprint=hash_json([observation_id,actor,approval_version,binding_version,name,url,tier,reason,brief_id,hosts,enabled,existing_source_id,expected_policy_version])
        with self.db.tx() as s:
            self._account(s,actor,'operator')
            prior=s.scalar(select(ScoutApproval).where(ScoutApproval.request_key==request_key))
            if prior:
                if prior.request_hash!=fingerprint or prior.actor!=actor:
                    raise Problem('批准请求标识已用于另一操作',409,'APPROVAL_KEY_CONFLICT')
                return prior.receipt
            o=s.get(ScoutObservation,observation_id)
            if not o or o.state!='RECEIVED':
                raise Problem('只能批准已接收的候选；未选或冲突内容不能作为来源',409,'CANDIDATE_NOT_RECEIVED')
            if approval_version!=hash_json([o.id,o.payload,o.state]):
                raise Problem('候选版本不符，请重新打开候选',409,'SCOUT_STALE_OBSERVATION')
            g=o.payload
            if g['blocking'] or o.conflict:
                raise Problem('候选身份或入口尚不能确定，请补充研究原件',409,'SCOUT_SOURCE_BLOCKED')
            if url not in g['seed_urls']:
                raise Problem('入口必须来自本次候选原件，不能暗中替换')
            c=s.get(ScoutCandidate,o.candidate_id); binding=s.get(ScoutBinding,c.id)
            if binding_version!=(binding.version if binding else 0):
                raise Problem('来源绑定已有变化，请刷新',409,'SCOUT_BINDING_CHANGED')
            bs=_briefs(g); chosen=next((b for b in bs if b['id']==brief_id),None)
            if brief_id is not None and not chosen:
                raise Problem('采集建议不属于本次候选版本')
            brief=json.dumps(chosen['payload'],ensure_ascii=False,indent=2) if chosen else ''
            if len(brief)>20000:
                raise Problem('采集建议超过20000字符；请选其他版本或保留为空，不截断原文',413,'BRIEF_SIZE')
            src=s.scalar(select(Source).where(Source.canonical_url==url))
            if src and str(src.source_id)!=existing_source_id:
                raise Problem('该入口已有来源，请明确选择关联已有来源',409,'SOURCE_LINK_REQUIRED')
            if existing_source_id:
                src=s.get(Source,existing_source_id)
                if not src or src.canonical_url!=url:
                    raise Problem('所选已有来源与本次入口不同，不能凭同名合并',409,'SOURCE_LINK_MISMATCH')
            if binding and str(binding.source_id)!=existing_source_id:
                raise Problem('候选已有来源映射，请明确关联原来源',409,'SOURCE_LINK_REQUIRED')
            if src:
                p=s.get(SourceProfile,src.source_id)
                if expected_policy_version!=(p.policy_version if p else 0):
                    raise Problem('来源政策版本已变化，请刷新',409,'SOURCE_POLICY_CHANGED')
                if src.authority_name!=name or src.tier!=tier:
                    raise Problem('已有来源的名称和角色与表单不同，请保留原身份；更改身份需单独维护',409,'SOURCE_IDENTITY_CHANGED')
                if not p:
                    p=SourceProfile(source_id=src.source_id);s.add(p)
                    p.policy_version=1
                else:
                    p.policy_version+=1
            else:
                sid=uid();src=Source(source_id=sid,public_id='src_'+sid.replace('-',''),canonical_url=url,authority_name=name,tier=tier)
                s.add(src);s.flush();p=SourceProfile(source_id=sid,policy_version=1);s.add(p)
            p.allowed_hosts=hosts;p.brief=brief;p.scheduling_enabled=enabled
            # Approval never silently creates a periodic paid schedule.
            p.interval_hours=0;p.next_due=None
            intelligence={'candidate_ref':c.namespace+'::'+c.candidate_key,'candidate_id':c.id,
                'candidate_revision_id':o.id,'batch_id':o.batch_id,'brief_id':brief_id,
                'brief_run_key':chosen['run_key'] if chosen else None,'brief_payload':chosen['payload'] if chosen else None,
                'meaning':'UNTRUSTED_NAVIGATION_REFERENCE_NOT_OFFICIAL_FACT_OR_AUTHORIZATION'}
            p.research_asset=intelligence
            if binding:
                binding.source_id=src.source_id;binding.observation_id=o.id;binding.brief_key=brief_id;binding.version+=1
            else:
                binding=ScoutBinding(candidate_id=c.id,source_id=src.source_id,observation_id=o.id,brief_key=brief_id,version=1)
                s.add(binding)
            receipt={'approval_id':uid(),'observation_id':o.id,'candidate_ref':intelligence['candidate_ref'],
                'system_source_id':str(src.source_id),'policy_version':p.policy_version,'binding_version':binding.version,
                'enabled':enabled,'brief_id':brief_id,'tasks_created':0,'approved_at':now().isoformat()}
            s.add(ScoutApproval(request_key=request_key,request_hash=fingerprint,actor=actor,receipt=receipt))
            s.add(ScoutEvent(batch_id=o.batch_id,candidate_id=c.id,type='SOURCE_APPROVED',payload={
                **receipt,'candidate_ref':intelligence['candidate_ref'],'transaction_id':receipt['approval_id']}))
            self._audit(s,actor,'SCOUT_SOURCE_APPROVE',o.batch_id,reason)
            s.flush()
            return receipt

    def scout_feedback(self, batch_id, *, actor):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator');b=self._scout_batch(s,batch_id)
            if not b.receipt:
                raise Problem('尚无已提交的系统反馈',409,'SCOUT_NO_RECEIPT')
            events=[]
            for event in s.scalars(select(ScoutEvent).where(ScoutEvent.batch_id==batch_id).order_by(ScoutEvent.created_at,ScoutEvent.id)):
                events.append({**event.payload,'event_id':event.id,'type':event.type,'occurred_at':aware(event.created_at).isoformat()})
            # Keep the external tool's 10k-event contract explicit rather than truncate.
            if len(events)>10000:
                raise Problem('事件超过单份反馈上限，需要分期导出',413,'SCOUT_FEEDBACK_LIMIT')
            return {'schema_version':'deepaha.scout-feedback.v1','issuer':'DeepAha',
                'instance_id':s.get(Meta,'instance_id').value,'environment':self.feedback_environment,
                'feedback_id':hash_json([batch_id,events]),'bundle_id':b.bundle_id,
                'package_sha256':b.package_sha256,'observed_at':events[-1]['occurred_at'] if events else b.receipt['received_at'],
                'events':events,'verification_method':'AUTHENTICATED_SYSTEM_READBACK; OFFLINE_FILE_IS_NOT_A_SIGNATURE',
                'source_receipt_id':b.receipt['transaction_id']}

    def _scout_source_event(self,s,source_id,enabled):
        if enabled:
            return  # schema v1 has no SOURCE_RESUMED event; do not misuse SOURCE_APPROVED
        for binding in s.scalars(select(ScoutBinding).where(ScoutBinding.source_id==source_id)):
            c=s.get(ScoutCandidate,binding.candidate_id);o=s.get(ScoutObservation,binding.observation_id)
            s.add(ScoutEvent(batch_id=o.batch_id,candidate_id=c.id,type='SOURCE_SUSPENDED',payload={
                'candidate_ref':c.namespace+'::'+c.candidate_key,'system_source_id':str(source_id),
                'transaction_id':uid(),'effect':'NEW_TASKS_ONLY_EXISTING_CONTENT_UNCHANGED'}))

    def _scout_task_event(self,s,task,success):
        """Record only a real local worker outcome for its frozen candidate version.

        Recovery is a separate attempt. A completed result is not content approval.
        No event is emitted for credential absence, idle or pre-dispatch policy changes.
        """
        frozen=s.get(TaskSourceContext,task.id)
        intelligence=frozen.payload.get('intelligence') if frozen else None
        if not intelligence:return
        observation=s.get(ScoutObservation,intelligence.get('candidate_revision_id',''))
        if not observation:return
        candidate=s.get(ScoutCandidate,observation.candidate_id)
        # Deterministic per task/attempt/outcome ID prevents retry event inflation.
        import uuid
        event_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"deepaha:scout:{task.id}:{task.attempts}:{success}"))
        if s.get(ScoutEvent,event_id):return
        s.add(ScoutEvent(id=event_id,batch_id=observation.batch_id,candidate_id=candidate.id,
            type='PRODUCTION_RUN_COMPLETED' if success else 'PRODUCTION_RUN_FAILED',payload={
                'candidate_ref':candidate.namespace+'::'+candidate.candidate_key,
                'system_source_id':str(task.source_id),'transaction_id':task.id,
                'task_id':task.id,'attempt':task.attempts,'revision_id':task.revision_id,
                'brief_id':intelligence.get('brief_id'),'status':task.status,
                'opportunity_approved':False,'scope':'LOCAL_RETURN_COLLECTION_AND_PROJECTION',
                'error_code':None if success else task.error_code}))
