"""Local result files, not Library uploads. No credentials or confirmation tokens."""
from __future__ import annotations
import os
import re
import tempfile
from pathlib import Path
from .contract import canonical_json, digest
from .errors import ImporterError


def immutable_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.read_bytes() == data: return
        raise ImporterError('LOCAL_FILE_CONFLICT', '本地同名结果文件内容不同，拒绝覆盖：' + str(path), 409)
    # Same-directory temp + hard link gives atomic publish without clobbering.
    fd, tmp = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ImporterError('LOCAL_FILE_CONFLICT', '结果文件出现并发内容冲突，拒绝覆盖。', 409)
        except OSError as exc:
            raise ImporterError('LOCAL_STORAGE_UNSUPPORTED', '结果目录不支持安全原子保存，请改用本机 NTFS/APFS/ext4 目录。', 500) from exc
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def _safe(value) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]', '_', str(value))[:120]


def receipt_markdown(receipt):
    demo = receipt['environment'] != 'PRODUCTION'
    def esc(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')
    lines = ['# DeepAha 来源资产导入回执', '',
             '**非生产回执：不是正式 DeepAha 入库证明，不要当作正式反馈上传给 Scout。**' if demo else '**服务器已回读确认本批次的导入结果。**', '',
             f"环境：`{esc(receipt['environment'])}`  ", f"批次：`{esc(receipt['run_key'])}`  ",
             f"系统批次 ID：`{esc(receipt['batch_id'])}`  ", f"完成时间：{esc(receipt['completed_at'])}  ",
             f"结果：`{esc(receipt['status'])}`", '',
             '| 类型 | 资产 | 动作 | 系统情报版本 | 来源批准状态 |', '|---|---|---|---:|---|']
    for item in receipt['items']:
        lines.append('| ' + ' | '.join(esc(item[k]) for k in ('kind', 'name', 'action', 'system_revision', 'approval_status')) + ' |')
    lines += ['', '## 提醒', '', '入库不等于批准正式机会事实；本导入器不会启动 WMA。',
              '回执已由程序生成。回传资料库是可选反馈，不影响已完成的导入。',
              '需要回传时上传同目录的 Receipt.json；请先核对其 environment 和 feedback_scope。', '',
              '## 内容校验', '', f"Handoff SHA-256：`{receipt['handoff_sha256']}`", '',
              f"包 SHA-256：`{receipt['package_hash']}`", '']
    return '\n'.join(lines).encode('utf-8')


def save_receipt(receipt: dict, directory: str | Path):
    directory = Path(directory).expanduser().resolve()
    prefix = f"DeepAha_{_safe(receipt['environment'])}_{_safe(receipt['run_key'])}_{_safe(receipt['receipt_key'])}_Receipt"
    json_path, md_path = directory / (prefix + '.json'), directory / (prefix + '.md')
    data = canonical_json(receipt) + b'\n'
    immutable_write(json_path, data)
    immutable_write(md_path, receipt_markdown(receipt))
    if json_path.read_bytes() != data:
        raise ImporterError('LOCAL_READBACK_MISMATCH', '回执保存后字节核对失败；可从服务器重新取回。', 500)
    return {'json_path': str(json_path), 'markdown_path': str(md_path)}


def save_pending(package, preview, directory):
    record = {'record_type': 'LOCAL_SUBMISSION_INTENT_NOT_A_RECEIPT',
              'run_key': package.run_key, 'environment': preview['environment'],
              'target_id': preview['target_id'], 'package_hash': package.package_hash,
              'approved_source_keys': preview.get('approve_sources', [])}
    key = digest(canonical_json(record))[:32]
    path = Path(directory) / 'pending' / (key + '.json')
    immutable_write(path, canonical_json(record) + b'\n')
    return path
