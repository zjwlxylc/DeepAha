"""Reuse the existing write-once, hash-verifying DeepAha object store."""
import hashlib
import errno
import time
import io
import json
import stat
import zipfile
from pathlib import PurePosixPath
from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.artifacts.object_store import ObjectIntegrityError
from .errors import Problem

MAX_ARCHIVE=32*1024*1024
MAX_FILE=20*1024*1024
MAX_TOTAL=100*1024*1024
MAX_FILES=100

def sha(b):return hashlib.sha256(b).hexdigest()

def unpack(data):
    if len(data)>MAX_ARCHIVE:raise Problem('压缩包超过32MB',413)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries=[e for e in z.infolist() if not e.is_dir()]
            if len(entries)>MAX_FILES:raise Problem('文件数量超过100个',413)
            total=0;out={}
            for e in entries:
                p=PurePosixPath(e.filename)
                if p.is_absolute() or any(x in ('..','.') for x in p.parts) or '\\' in e.filename or ':' in e.filename or '\x00' in e.filename or str(p)!=e.filename or stat.S_ISLNK(e.external_attr>>16):
                    raise Problem('压缩包包含不安全的文件路径',400,'UNSAFE_ARCHIVE')
                if e.filename in out:raise Problem('压缩包存在重复文件名')
                if e.flag_bits&1:raise Problem('不支持加密压缩包')
                if e.file_size>MAX_FILE or e.file_size/max(1,e.compress_size)>500:raise Problem('文件过大或压缩比例异常',413)
                total+=e.file_size
                if total>MAX_TOTAL:raise Problem('解压内容超过100MB',413)
                with z.open(e) as f:b=f.read(MAX_FILE+1)
                if len(b)>MAX_FILE or len(b)!=e.file_size:raise Problem('文件读取不完整',400)
                out[e.filename]=b
            # Accept one common outer folder; never overwrite duplicate basenames.
            roots=[k for k in out if k.endswith('opportunities.json')]
            if len(roots)==1:
                prefix=roots[0][:-len('opportunities.json')]
                if prefix and all(k.startswith(prefix) for k in out):out={k[len(prefix):]:v for k,v in out.items()}
            for base in ('opportunities.json','evidence.json','report.md'):
                if base not in out:
                    matches=[k for k in out if k.endswith('/'+base)]
                    if len(matches)==1:out[base]=out[matches[0]]
            return out
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError,OSError) as e:raise Problem('无法安全读取压缩包',400,'UNREADABLE_ARCHIVE') from e

class ArchiveStore:
    def __init__(self,root):
        self.backend=LocalFileObjectStore(root=root,bucket='deepaha-raw')
        self.backend.ensure_bucket()
    def save(self,files):
        manifest={}
        for name,b in files.items():
            h=sha(b);key=f'{h[:2]}/{h}'
            # Concurrent investigations can legitimately save identical bytes.
            # Retry ONLY the existing store's local non-blocking lock error.
            # Never retry corrupt data, remote prompts, or bypass its SHA checks.
            until=time.monotonic()+2.0
            while True:
                try:
                    self.backend.put_bytes_if_absent(key=key,content=b,media_type='application/octet-stream',sha256=h)
                    break
                except ObjectIntegrityError as error:
                    busy=(str(error)=='object write is already in progress'
                          and isinstance(error.__cause__,OSError)
                          and error.__cause__.errno in {errno.EAGAIN,errno.EACCES,errno.EBUSY})
                    remaining=until-time.monotonic()
                    if not busy or remaining<=0:raise
                    time.sleep(min(.025,remaining))
            manifest[name]={'key':key,'sha256':h,'size':len(b)}
        return manifest
    def load(self,manifest):return {k:self.backend.get_bytes(key=v['key']) for k,v in manifest.items()}
    def one(self,manifest,name):
        if name not in manifest:raise Problem('原件不存在',404)
        return self.backend.get_bytes(key=manifest[name]['key'])
