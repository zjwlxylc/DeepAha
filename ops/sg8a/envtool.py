#!/usr/bin/env python3
"""Read a root-owned DeepAha EnvironmentFile without shell expansion."""
from __future__ import annotations
import ast
import os
from pathlib import Path
import re
import sys

KEY=re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

def load(path):
    out={}
    for number,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(),1):
        stripped=line.strip()
        if not stripped or stripped.startswith('#'):continue
        if '=' not in line:raise SystemExit(f'invalid environment line {number}')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not KEY.fullmatch(key):raise SystemExit(f'invalid environment key on line {number}')
        if len(value)>=2 and value[0]==value[-1] and value[0] in "'\"":
            try:value=ast.literal_eval(value)
            except (ValueError,SyntaxError):raise SystemExit(f'invalid quoted value on line {number}')
        out[key]=value
    return out

def main():
    if len(sys.argv)<4 or sys.argv[1] not in ('get','run'):
        raise SystemExit('usage: envtool.py get FILE KEY | envtool.py run FILE COMMAND [ARGS...]')
    mode,path=sys.argv[1],sys.argv[2];values=load(path)
    if mode=='get':
        key=sys.argv[3]
        if key not in values:raise SystemExit(f'missing environment key: {key}')
        print(values[key]);return
    command=sys.argv[3:]
    environment=os.environ.copy();environment.update(values)
    os.execvpe(command[0],command,environment)
if __name__=='__main__':main()
