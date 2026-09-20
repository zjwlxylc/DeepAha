#!/usr/bin/env python3
"""Read-only validation of a delivered source tree; no network, no database."""
import hashlib,json,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
def main():
    manifest=json.loads((ROOT/'FILE_MANIFEST.json').read_text(encoding='utf-8'))
    errors=[];seen=set()
    for item in manifest['files']:
        rel=PurePosixPath(item['path'])
        if rel.is_absolute() or '..' in rel.parts or str(rel) in seen:
            errors.append('unsafe/duplicate manifest path');continue
        seen.add(str(rel));file=ROOT/str(rel)
        if not file.resolve().is_relative_to(ROOT):errors.append(str(rel)+': outside tree');continue
        if not file.is_file():errors.append(str(rel)+': missing');continue
        with file.open('rb') as handle:sha=hashlib.file_digest(handle,'sha256').hexdigest()
        if sha!=item['sha256'] or file.stat().st_size!=item['bytes']:errors.append(str(rel)+': mismatch')
    if len(seen)!=manifest['file_count']:errors.append('manifest count mismatch')
    print(json.dumps({'status':'FAIL' if errors else 'PASS','checked_files':len(seen),'errors':errors},ensure_ascii=False,indent=2))
    return 1 if errors else 0
if __name__=='__main__':raise SystemExit(main())
