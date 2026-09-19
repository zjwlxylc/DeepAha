"""Bounded offline file/ZIP reader. Never executes or downloads asset content."""
from __future__ import annotations
import io
import os
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from ..contract import parse_json, digest, canonical_json
from ..errors import ImporterError
from .normalize import infer_namespace

@dataclass(frozen=True)
class Limits:
    input_bytes: int = 100 * 1024 * 1024
    member_bytes: int = 50 * 1024 * 1024
    expanded_bytes: int = 500 * 1024 * 1024
    json_bytes: int = 8 * 1024 * 1024
    members: int = 10000
    ratio: int = 1000

@dataclass
class Blob:
    name: str
    data: bytes
    input_name: str
    input_sha256: str
    namespace_hint: str = 'AUTO'
    @property
    def sha256(self): return digest(self.data)
    @property
    def locator(self): return self.input_sha256[:16] + '/' + self.name
    def metadata(self):
        return {'path':self.name,'input_name':self.input_name,'input_sha256':self.input_sha256,
                'sha256':self.sha256,'size_bytes':len(self.data),'locator':self.locator}

@dataclass
class InputSet:
    files: list[Blob] = field(default_factory=list)
    handoffs: list[dict] = field(default_factory=list)
    states: list[dict] = field(default_factory=list)
    originals: list[Blob] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)


def safe_member(name):
    if not isinstance(name,str) or len(name)>800 or '\\' in name or any(ord(c)<32 for c in name):
        raise ImporterError('UNSAFE_ARCHIVE_PATH','压缩包含不安全的路径。')
    name=unicodedata.normalize('NFC',name)
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or re.match(r'^[a-zA-Z]:',name) or not path.parts:
        raise ImporterError('UNSAFE_ARCHIVE_PATH','压缩包含绝对路径或越界路径。')
    if any(':' in part or part.endswith((' ','.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',part) for part in path.parts):
        raise ImporterError('UNSAFE_ARCHIVE_PATH','压缩包路径不能安全用于Windows。')
    return str(path)


def _read_file(path, limit):
    if path.is_symlink(): raise ImporterError('UNSAFE_FILE','不读取符号链接。')
    # Check every parent rather than following an out-of-root link.
    if any(p.is_symlink() for p in path.parents): raise ImporterError('UNSAFE_FILE','文件路径经过符号链接。')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size>limit: raise ImporterError('FILE_LIMIT','文件不是普通文件或超过100MiB。')
        raw=f.read(limit+1)
        if len(raw)>limit:raise ImporterError('FILE_LIMIT','文件超出允许大小。')
        return raw


def load_inputs(paths, namespace='AUTO', limits=None):
    limits=limits or Limits(); result=InputSet(); total=0
    def add(blob):
        nonlocal total
        total+=len(blob.data)
        if total>limits.expanded_bytes or len(result.files)>=limits.members:
            raise ImporterError('BATCH_LIMIT','本批展开大小或文件数量超过保护上限。请分批处理。')
        result.files.append(blob)
        if blob.name.lower().endswith('.json'):
            if len(blob.data)>limits.json_bytes: raise ImporterError('JSON_LIMIT','研究JSON超过8MiB，请保留原件并拆分交接。')
            obj=parse_json(blob.data,limits.json_bytes)
            if not isinstance(obj,dict): return
            schema=obj.get('schema_version','')
            if schema=='deepaha.research-handoff.v1':
                raise ImporterError('REVIEW_BUNDLE_NOT_RESEARCH_INPUT','这是一份已导出的审核交接包，不是原始Scout包。继续审核请打开左侧原会话；跨电脑请先解压originals后选择原始JSON/ZIP，已有意见在Decisions.json中保留。已停止，避免只读到部分来源。')
            is_handoff=isinstance(obj.get('run_metadata'),dict) and isinstance(obj.get('source_candidates'),list)
            if is_handoff:
                run=obj['run_metadata'].get('run_key')
                if not isinstance(run,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}',run):
                    raise ImporterError('INVALID_RUN_KEY','研究包缺少合法批次标识。')
                if schema!='deepaha.source-intelligence.run.v2.2':
                    result.warnings.append({'code':'UNSUPPORTED_HANDOFF_SCHEMA','file':blob.locator,'schema':schema});return
                result.handoffs.append({'data':obj,'blob':blob,'namespace':infer_namespace(run,blob.namespace_hint),'run_key':run})
            elif 'state' in str(schema).lower() or blob.name.lower().endswith('_state.json'):
                run=str(obj.get('run_key') or obj.get('run_metadata',{}).get('run_key') or '')
                result.states.append({'data':obj,'blob':blob,'namespace':infer_namespace(run,blob.namespace_hint),'run_key':run})
    for value in paths:
        # Explicit per-input namespaces may be supplied by the batch UI/CLI.
        if isinstance(value,tuple): value,hint=value
        else: hint=namespace
        path=Path(value).expanduser()
        if path.is_dir():
            candidates=sorted(path.rglob('*')); directory_files=[]
            if len(candidates)>limits.members:raise ImporterError('BATCH_LIMIT','目录成员过多。')
            for child in candidates:
                if child.is_symlink():raise ImporterError('UNSAFE_FILE','目录中存在符号链接，未读取。')
                if not child.is_file():continue
                raw=_read_file(child,limits.member_bytes)
                rel=safe_member(child.relative_to(path).as_posix())
                directory_files.append((rel,raw))
            owner=digest(canonical_json([{'path':name,'sha256':digest(raw)} for name,raw in directory_files]))
            for rel,raw in directory_files:
                blob=Blob(rel,raw,path.name,owner,hint)
                result.originals.append(blob);add(blob)
            continue
        if not path.is_file():raise ImporterError('INPUT_MISSING','所选文件不存在。')
        raw=_read_file(path,limits.input_bytes); owner=digest(raw)
        original=Blob(safe_member(path.name),raw,path.name,owner,hint);result.originals.append(original)
        if path.suffix.lower()!='.zip': add(original);continue
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos=z.infolist()
                if len(infos)>limits.members:raise ImporterError('ZIP_LIMIT','压缩包成员过多。')
                seen=set()
                for info in infos:
                    name=safe_member(info.filename.rstrip('/'))
                    if name.casefold() in seen:raise ImporterError('ZIP_DUPLICATE_PATH','压缩包有重复或大小写冲突的文件路径，拒绝覆盖。')
                    seen.add(name.casefold())
                    mode=(info.external_attr>>16)&0xFFFF
                    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
                        raise ImporterError('UNSAFE_ARCHIVE_MEMBER','压缩包中存在链接或特殊文件。')
                    if info.flag_bits&1:raise ImporterError('ENCRYPTED_ARCHIVE','不处理加密成员，请提供原始可读研究包。')
                    if info.is_dir():continue
                    if info.file_size>limits.member_bytes or info.file_size/max(1,info.compress_size)>limits.ratio:
                        raise ImporterError('ZIP_LIMIT','压缩包单文件大小或压缩比例超过保护上限。')
                    with z.open(info) as stream: content=stream.read(limits.member_bytes+1)
                    if len(content)>limits.member_bytes or len(content)!=info.file_size:raise ImporterError('ZIP_LIMIT','压缩包实际展开字节不符。')
                    add(Blob(name,content,path.name,owner,hint))
                    if name.lower().endswith('.zip'):
                        result.warnings.append({'code':'NESTED_ARCHIVE_RETAINED_OPAQUE','file':name,'note':'嵌套压缩附件按原件保存，不执行、不展开。'})
        except (zipfile.BadZipFile,NotImplementedError,RuntimeError,OSError) as exc:
            if isinstance(exc,ImporterError):raise
            raise ImporterError('INVALID_ARCHIVE','压缩包损坏或使用不支持的格式。') from exc
    return result
