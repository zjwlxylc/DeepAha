#!/usr/bin/env python3
"""Create a full source ZIP with content manifest and exact uploaded-parent delta."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
IGNORED={'__pycache__','.pytest_cache','.git','.venv','.venv-product','node_modules','.ruff_cache','.mypy_cache'}
SUFFIXES={'.pyc','.pyo','.ttf','.otf','.ttc','.woff','.woff2'}
META={'FILE_MANIFEST.json','FILE_MANIFEST.sha256'}

def files():
 out=[]
 for p in ROOT.rglob('*'):
  if p.is_symlink():raise RuntimeError('Refuse source symlink: '+str(p))
  if not p.is_file() or set(p.relative_to(ROOT).parts)&IGNORED or p.suffix.lower() in SUFFIXES:continue
  if p.name=='.env' or p.suffix.lower() in ('.db','.sqlite','.sqlite3'):raise RuntimeError('Private runtime data must not enter source ZIP: '+str(p))
  out.append(p)
 return sorted(out,key=lambda p:p.relative_to(ROOT).as_posix())

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent-zip',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 parent={}
 with zipfile.ZipFile(a.parent_zip) as z:
  bad=z.testzip()
  if bad:raise RuntimeError('Parent CRC failed: '+bad)
  for info in z.infolist():
   if info.is_dir():continue
   rel=info.filename.split('/',1)[1]
   parent[rel]=hashlib.sha256(z.read(info)).hexdigest()
 digest=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
 current={p.relative_to(ROOT).as_posix():digest(p) for p in files() if p.relative_to(ROOT).as_posix() not in META|{'CHANGESET_MOBILE_R3.json'}}
 diff=[]
 for name in sorted(set(parent)|set(current)):
  if name in META|{'CHANGESET_MOBILE_R3.json'}:continue
  if parent.get(name)==current.get(name):continue
  diff.append({'path':name,'action':'added' if name not in parent else 'removed' if name not in current else 'modified','before_sha256':parent.get(name),'after_sha256':current.get(name)})
 changes={'iteration':'mobile-r3-services-20260921','parent_zip_sha256':digest(a.parent_zip),'parent_zip_bytes':a.parent_zip.stat().st_size,'basis':'Actual uploaded Mobile R2 ZIP, not remote main','remote_writes':False,'deployed':False,'entries':diff,'excluded_generated_meta':sorted(META|{'CHANGESET_MOBILE_R3.json'})}
 (ROOT/'CHANGESET_MOBILE_R3.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 manifest={p.relative_to(ROOT).as_posix():digest(p) for p in files() if p.relative_to(ROOT).as_posix() not in META}
 tree_manifest={'release':'3.8.0-rc1','extension':'mobile-r3-services-20260921','parent_zip_sha256':changes['parent_zip_sha256'],'file_count':len(manifest),'files':[{'path':name,'sha256':value,'bytes':(ROOT/name).stat().st_size} for name,value in manifest.items()]}
 (ROOT/'FILE_MANIFEST.json').write_text(json.dumps(tree_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (ROOT/'FILE_MANIFEST.sha256').write_text(''.join(h+'  '+name+'\n' for name,h in manifest.items()),encoding='utf-8')
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(a.output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in files():z.write(p,'DeepAha_Mobile_R3/'+p.relative_to(ROOT).as_posix())
 with zipfile.ZipFile(a.output) as z:
  bad=z.testzip()
  if bad:raise RuntimeError('Output CRC failed: '+bad)
 receipt={'artifact':a.output.name,'bytes':a.output.stat().st_size,'sha256':digest(a.output),'manifest_files':len(manifest),'entries':len(manifest)+2,'changes':{k:sum(x['action']==k for x in diff) for k in ['added','modified','removed']},'zip_crc':'PASS','reextracted_tests':'PENDING'}
 print(json.dumps(receipt,ensure_ascii=False,indent=2))
 return 0
if __name__=='__main__':raise SystemExit(main())
