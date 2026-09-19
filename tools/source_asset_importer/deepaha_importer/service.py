"""Single deterministic import service shared by desktop, CLI and HTTP adapters."""
from __future__ import annotations
import uuid
from collections import Counter
from datetime import datetime, timezone
from .contract import Package, canonical_json, digest
from .errors import ImporterError
from .integration import NoProductionAuthority
from .repository import decode

POLICY_VERSION = 'import-policy-v1'


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class ImportService:
    def __init__(self, repository, signer, environment='STAGING', authority=None):
        if environment not in {'DEMO', 'TEST', 'STAGING', 'PRODUCTION'}:
            raise ImporterError('INVALID_ENVIRONMENT', '目标环境标识不受支持。', 500)
        if environment == 'PRODUCTION' and getattr(repository, 'reference_backend', True):
            raise ImporterError('PRODUCTION_NOT_INTEGRATED', '参考暂存仓储不能充当正式 DeepAha；需先完成主项目适配。', 503)
        self.repo, self.signer, self.environment = repository, signer, environment
        self.authority = authority or NoProductionAuthority()

    def capabilities(self, principal):
        principal.require('scout:preview')
        with self.repo.transaction() as tx:
            target = tx.meta()['target_id']
        return {'api_contract': 'deepaha.scout-import.api.v1', 'environment': self.environment,
                'target_id': target, 'reference_backend': getattr(self.repo, 'reference_backend', True),
                'supports_source_approval': self.authority.supports_approval and 'scout:approve' in principal.scopes,
                'can_import': 'scout:import' in principal.scopes, 'receipt_upload_required': False,
                'supported_handoff_schema': 'deepaha.source-intelligence.run.v2.2',
                'producer': principal.producer, 'subject': principal.subject}

    def _approval_keys(self, package, principal, keys):
        if keys is None: keys = []
        if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
            raise ImporterError('INVALID_APPROVAL', '批准来源清单格式错误。', 422)
        keys = sorted(set(keys))
        if keys:
            principal.require('scout:approve')
            if not self.authority.supports_approval:
                raise ImporterError('APPROVAL_NOT_CONNECTED', '服务端没有接入正式来源批准功能；本次只可保存候选。', 409)
            available = {a.key for a in package.assets('source')}
            if not set(keys) <= available:
                raise ImporterError('INVALID_APPROVAL', '不能批准不在本次交付包中的来源。', 422)
        return keys

    def preview(self, package: Package, principal, approve_sources=None):
        principal.require('scout:preview')
        package = Package.from_bytes(package.raw, package.files)
        approved = self._approval_keys(package, principal, approve_sources)
        with self.repo.transaction() as tx:
            plan = self._plan(tx, package, principal)
        token = None
        if not plan['conflicts']:
            token = self.signer.sign(self._claims(plan, package, principal, approved))
        counts = dict(Counter(x['action'] for x in plan['items']))
        return {k: plan[k] for k in ('run_key', 'environment', 'target_id', 'generation', 'items', 'conflicts', 'warnings', 'already_imported')} | {
            'counts': counts, 'can_commit': not plan['conflicts'], 'confirmation_token': token,
            'expires_in_seconds': self.signer.ttl if token else None,
            'package_hash': package.package_hash, 'handoff_sha256': package.sha256,
            'approve_sources': approved, 'automatic_collection': False,
        }

    def _claims(self, plan, package, principal, approved):
        return {'policy': POLICY_VERSION, 'subject': principal.subject, 'producer': principal.producer,
                'environment': self.environment, 'target_id': plan['target_id'], 'run_key': package.run_key,
                'package_hash': package.package_hash, 'generation': plan['generation'],
                'plan_hash': digest(canonical_json(plan['items'])),
                'actions': ['IMPORT_CANDIDATES'], 'approve_sources': approved}

    def _plan(self, tx, package, principal):
        meta = tx.meta(); records, aliases = tx.snapshot(principal.producer)
        by_id = {r['asset_id']: r for r in records}
        by_key = {(r['kind'], r['asset_key']): r for r in records}
        for key, asset_id in aliases.items(): by_key[key] = by_id[asset_id]
        by_identity = {(r['kind'], r['identity_hash']): r for r in records if r['identity_hash']}
        for (kind, key), asset_id in aliases.items():
            if kind == 'source_identity': by_identity[('source', key)] = by_id[asset_id]
        plan = {'run_key': package.run_key, 'environment': self.environment, 'target_id': meta['target_id'],
                'generation': meta['generation'], 'items': [], 'conflicts': [],
                'warnings': list(package.data['warnings']), 'already_imported': False}
        if self.environment in {'DEMO', 'TEST'}:
            plan['warnings'].append(self.environment + '_ONLY：不是正式系统入库，回执不得充当正式反馈。')
        if package.data['run_metadata']['result_status'] != 'COMPLETE':
            plan['warnings'].append('研究结果不是 COMPLETE；仅导入已完整交付的候选，不补造未完成研究。')
        existing_batch = tx.batch(principal.producer, package.run_key)
        if existing_batch:
            if existing_batch['package_hash'] != package.package_hash:
                plan['conflicts'].append({'code': 'BATCH_CONTENT_CONFLICT', 'message': '同 run_key 已存在不同内容，须另建更正批次。'})
            else:
                plan['already_imported'] = True
                old = decode(existing_batch['receipt_json'])
                plan['items'] = old['items']
            return plan
        assets = package.assets()
        local_keys = {(a.kind, a.key) for a in assets}
        for kind, key in sorted(package.references()):
            if (kind, key) not in local_keys and (kind, key) not in by_key:
                plan['conflicts'].append({'code': 'UNRESOLVED_REFERENCE', 'kind': kind, 'key': key,
                                          'message': '引用在本包和现有情报库中均不存在。'})
        seen_identity = {}
        for asset in assets:
            r = asset.payload; current = by_key.get((asset.kind, asset.key))
            identity_match = by_identity.get((asset.kind, asset.identity)) if asset.identity else None
            code, reason, action = None, '', 'ADD'
            if asset.identity:
                if asset.identity in seen_identity:
                    code, reason = 'DUPLICATE_SOURCE_IN_PACKAGE', '本包多个候选指向同一机构同一入口，请先明确去重。'
                seen_identity[asset.identity] = asset.key
                if current and identity_match and current['asset_id'] != identity_match['asset_id']:
                    code, reason = 'IDENTITY_CONFLICT', '候选键和入口身份分别指向不同资产。'
            system_status = None
            if asset.kind == 'source' and r.get('system_source_id'):
                system_status = self.authority.resolve(tx, principal, r['system_source_id'])
                if system_status is None:
                    code, reason = 'SYSTEM_SOURCE_UNRESOLVED', '无法在宿主权威服务核验给定的正式 Source ID。'
            if current is None and identity_match:
                current = identity_match
                if asset.content_hash == current['content_hash']:
                    action, reason = 'DUPLICATE', '不同外部键指向相同机构入口且内容相同；保存别名，不新建来源。'
                else:
                    code, reason = 'IDENTITY_REVIEW_REQUIRED', '相同机构入口但内容或版本不同，须确认已有键及版本后重交。'
            elif current is not None:
                if asset.content_hash == current['content_hash'] and (asset.external_revision is None or asset.external_revision == current['external_revision']):
                    action, reason = 'NO_CHANGE', '已有相同内容；本轮原始记录仍随批次保留。'
                else:
                    system_ok = asset.system_base_revision is not None and asset.system_base_revision == current['system_revision']
                    external_ok = (asset.base_revision is not None and current['external_revision'] is not None
                                   and asset.base_revision == current['external_revision'])
                    # An explicitly supplied system baseline must be respected even if Scout baseline matches.
                    if asset.system_base_revision is not None and not system_ok:
                        code, reason = 'SYSTEM_VERSION_CONFLICT', '系统基础版本已变化，拒绝旧版本覆盖。'
                    elif not (system_ok or external_ok):
                        code, reason = 'BASE_REVISION_REQUIRED', '更新需匹配实际 Scout base_revision 或回执中的 system_base_revision；两者不能混用。'
                    elif asset.base_revision is not None and not external_ok:
                        code, reason = 'SCOUT_VERSION_CONFLICT', 'Scout 基础版本与库内外部版本不符。'
                    elif asset.external_revision is not None and asset.external_revision == current['external_revision']:
                        code, reason = 'SCOUT_REVISION_REUSE', '同一外部版本不能对应不同内容。'
                    else:
                        action, reason = 'UPDATE', '建立新的研究版本，旧版和生产有效版本不被删除。'
            elif asset.base_revision is not None or asset.system_base_revision is not None:
                code, reason = 'MISSING_BASE_ASSET', '更新依赖的旧资产不在当前库中，不能将更新伪装成新建。'
            if current and asset.kind == 'source' and current['payload'].get('system_source_id') is not None and current['payload']['system_source_id'] != r.get('system_source_id'):
                code, reason = 'FORMAL_ID_CONFLICT', '不能通过研究更新重新绑定或删除已知正式 Source ID。'
            if code:
                action = 'CONFLICT'
                plan['conflicts'].append({'code': code, 'kind': asset.kind, 'key': asset.key, 'message': reason})
            plan['items'].append({'kind': asset.kind, 'key': asset.key,
                'name': r.get('source_name') or r.get('title') or r.get('description') or r.get('theme') or r.get('text') or asset.key,
                'action': action, 'reason': reason or '新增待审核研究资产。',
                'changes': {k: {'before': current['payload'].get(k), 'after': r.get(k)}
                            for k in sorted(set(current['payload']) | set(r))
                            if current['payload'].get(k) != r.get(k)} if current else {},
                'asset_id': current['asset_id'] if current else None,
                'base_system_revision': current['system_revision'] if current else None,
                'system_revision': (current['system_revision'] + (action == 'UPDATE')) if current else 1,
                'scout_revision': asset.external_revision if action in {'ADD', 'UPDATE'} else current['external_revision'] if current else None,
                'system_source_id': system_status.get('system_source_id') if system_status else None,
                'approval_status': system_status.get('approval_status', 'UNKNOWN') if system_status else 'PENDING_REVIEW',
                'collection_enabled': bool(system_status.get('collection_enabled', False)) if system_status else False})
        return plan

    def commit(self, package, principal, confirmation_token, confirmed, expected_environment, approve_sources=None):
        principal.require('scout:import')
        if confirmed is not True:
            raise ImporterError('CONFIRMATION_REQUIRED', '需要用户明确确认本批次和目标环境。', 400)
        if expected_environment != self.environment:
            raise ImporterError('ENVIRONMENT_MISMATCH', '所确认环境与服务端环境不一致。', 409)
        package = Package.from_bytes(package.raw, package.files)
        approved = self._approval_keys(package, principal, approve_sources)
        claims = self.signer.verify(confirmation_token)
        required = {'policy': POLICY_VERSION, 'subject': principal.subject, 'producer': principal.producer,
                    'environment': self.environment, 'run_key': package.run_key, 'package_hash': package.package_hash,
                    'actions': ['IMPORT_CANDIDATES'], 'approve_sources': approved}
        if any(claims.get(k) != v for k, v in required.items()):
            raise ImporterError('CONFIRMATION_MISMATCH', '确认与文件、身份、环境或批准动作不一致，请重新预览。', 409)
        with self.repo.transaction(write=True) as tx:
            meta = tx.meta()
            if meta['target_id'] != claims.get('target_id'):
                raise ImporterError('TARGET_MISMATCH', '服务端存储目标已变化，请重新预览。', 409)
            old = tx.batch(principal.producer, package.run_key)
            if old:
                if old['package_hash'] != package.package_hash:
                    raise ImporterError('BATCH_CONTENT_CONFLICT', '相同批次存在其他内容。', 409)
                old_receipt = decode(old['receipt_json'])
                if old_receipt['approved_source_keys'] != approved:
                    raise ImporterError('APPROVAL_REPLAY_CONFLICT', '已导入批次不能通过重送附加新批准；请走宿主审核流程。', 409)
            else:
                if claims.get('generation') != meta['generation']:
                    raise ImporterError('STALE_PREVIEW', '预览后情报库已有变化，请重新预览。', 409)
                plan = self._plan(tx, package, principal)
                if plan['conflicts']:
                    raise ImporterError('IMPORT_CONFLICT', '存在冲突，整批未写入。', 409, plan['conflicts'])
                if digest(canonical_json(plan['items'])) != claims.get('plan_hash'):
                    raise ImporterError('PLAN_CHANGED', '当前导入计划已变化，请重新预览。', 409)
                self._apply(tx, package, principal, plan, approved)
        # Fresh transaction after durable commit: not just trusting a method return code.
        result = self.receipt(package.run_key, principal)
        if result['package_hash'] != package.package_hash:
            raise ImporterError('READBACK_MISMATCH', '提交后回读与本次包不一致，须人工核查。', 500)
        return result

    def _apply(self, tx, package, principal, plan, approved):
        batch_id = str(uuid.uuid4()); created_at = now_iso()
        tx.insert_batch(batch_id, principal.producer, package, principal.subject, created_at)
        source_records = []; items = []
        for asset, item in zip(package.assets(), plan['items'], strict=True):
            output = dict(item)
            asset_id = item['asset_id'] or str(uuid.uuid4()); output['asset_id'] = asset_id
            if item['action'] in {'ADD', 'UPDATE'}:
                record = {'asset_id': asset_id, 'producer': principal.producer, 'kind': asset.kind,
                          'asset_key': asset.key, 'identity_hash': asset.identity,
                          'external_revision': asset.external_revision, 'system_revision': item['system_revision'],
                          'content_hash': asset.content_hash, 'payload': asset.payload}
                tx.save_asset(record, batch_id, item['action'] == 'ADD')
            tx.add_alias(principal.producer, asset.kind, asset.key, asset_id)
            if asset.kind == 'source' and asset.identity:
                tx.add_alias(principal.producer, 'source_identity', asset.identity, asset_id)
            if asset.kind == 'source' and asset.key in approved:
                source_records.append({'asset_id': asset_id, 'payload': asset.payload,
                                       'system_revision': item['system_revision']})
            items.append(output)
        # References resolve only after every asset is saved, within the same transaction.
        records, aliases = tx.snapshot(principal.producer)
        refs = {(r['kind'], r['asset_key']): r['asset_id'] for r in records} | aliases
        for kind, key in sorted(package.references()):
            tx.add_link(batch_id, kind, key, refs[(kind, key)])
        for name, content in package.files: tx.add_file(batch_id, name, content, digest(content))
        if source_records:
            statuses = self.authority.approve_in_transaction(tx, principal, source_records)
            for item in items:
                if item['kind'] == 'source' and item['key'] in approved:
                    status = statuses.get(item['asset_id'])
                    if not isinstance(status, dict) or not status.get('system_source_id') or type(status.get('collection_enabled')) is not bool or not status.get('approval_status'):
                        raise ImporterError('AUTHORITY_RESULT_INVALID', '宿主批准结果不完整，整批回滚。', 500)
                    item.update({k: status[k] for k in ('system_source_id', 'approval_status', 'collection_enabled')})
        receipt = {
            'schema_version': 'deepaha.source-intelligence.import-receipt.v1',
            'receipt_key': str(uuid.uuid4()), 'run_key': package.run_key, 'batch_id': batch_id,
            'producer': principal.producer, 'target_id': plan['target_id'], 'environment': self.environment,
            'reference_backend': getattr(self.repo, 'reference_backend', True),
            'actor': principal.subject, 'completed_at': created_at, 'handoff_sha256': package.sha256,
            'package_hash': package.package_hash,
            'status': 'IMPORTED' if self.environment == 'PRODUCTION' else self.environment + '_IMPORTED',
            'items': items, 'counts': dict(Counter(i['action'] for i in items)),
            'approved_source_keys': approved, 'wma_automatically_started': False,
            'files': [{'relative_path': n, 'sha256': digest(b), 'size_bytes': len(b)} for n, b in package.files],
            'warnings': plan['warnings'], 'receipt_upload_required': False,
            'feedback_scope': 'PRODUCTION' if self.environment == 'PRODUCTION' else 'NON_PRODUCTION_DO_NOT_USE_AS_LIVE_FEEDBACK',
        }
        tx.finalize(batch_id, receipt)

    def receipt(self, run_key, principal):
        # Importers must be able to recover their own operation even with read-only views removed.
        if not ({'scout:read', 'scout:import'} & principal.scopes): principal.require('scout:read')
        with self.repo.transaction() as tx:
            row = tx.batch(principal.producer, run_key)
            if row is None:
                raise ImporterError('BATCH_NOT_FOUND', '当前来源命名空间中没有已完成的该批次。', 404)
            receipt = decode(row['receipt_json'])
        if not receipt.get('receipt_key'):
            raise ImporterError('RECEIPT_NOT_READY', '批次回执尚未完整生成。', 503)
        return receipt
