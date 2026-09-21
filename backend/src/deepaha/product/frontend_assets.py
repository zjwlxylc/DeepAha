"""Consistent static build identity; stdlib only, no data/secret access."""
from pathlib import Path
import hashlib
import json
import re


def build_release(directory: Path) -> tuple[str, dict]:
    html=re.sub(r'/product/_v/[^/]+/','/product/',(directory/'index.html').read_text(encoding='utf-8'))
    digest=hashlib.sha256(html.encode())
    files={}
    for file in sorted([*directory.glob('*.js'),*directory.glob('*.css')]):
        content=file.read_bytes()
        files[file.name]=hashlib.sha256(content).hexdigest()
        digest.update(file.name.encode()+b'\0'+content)
    build='mobile-r3-'+digest.hexdigest()[:12]
    versioned=re.sub(r'(["\'])/product/([^"\']+\.(?:js|css))(["\'])',
                     lambda m:m[1]+'/product/_v/'+build+'/'+m[2]+m[3],html)
    return versioned,{'iteration':'mobile-r3','build':build,'files':files}


def validate_release(directory: Path) -> str:
    try:
        html,expected=build_release(directory)
        actual=json.loads((directory/'asset-release.json').read_text(encoding='utf-8'))
        if actual!=expected or (directory/'index.html').read_text(encoding='utf-8')!=html:
            raise ValueError('content mismatch')
        return expected['build']
    except (OSError,ValueError,KeyError) as error:
        raise RuntimeError('ASSET_BUILD_STALE: run python scripts/services_r3/build_assets.py before starting') from error
