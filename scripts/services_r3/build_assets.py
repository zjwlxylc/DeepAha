#!/usr/bin/env python3
"""Build the R3 coherent namespace for all ES modules; no install, data or external access."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.frontend_assets import build_release,validate_release
PUBLIC=ROOT/'web/public/product'


def build(check=False):
    if check:
        name=validate_release(PUBLIC)
    else:
        html,manifest=build_release(PUBLIC)
        (PUBLIC/'index.html').write_text(html,encoding='utf-8')
        (PUBLIC/'asset-release.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        name=manifest['build']
    print(name)
    return name

if __name__=='__main__':build('--check' in sys.argv)
