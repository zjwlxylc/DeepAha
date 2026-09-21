"""Worker liveness and dispatch outcome telemetry; never changes admission or tasks."""
import asyncio
import json
import os
import re
import traceback
from .models import Meta, now
from .auth import aware


def safe_error(error):
    code=getattr(error,'code',type(error).__name__)
    return code if isinstance(code,str) and re.fullmatch(r'[A-Za-z0-9_]{1,100}',code) else 'WORKER_ERROR'


def log_error(error):
    # Frame locations only: exception messages/source lines may contain credentials.
    frames=[{'file':os.path.basename(f.filename),'line':f.lineno,'function':f.name}
            for f in traceback.extract_tb(error.__traceback__)]
    print(json.dumps({'state':'WORKER_UNAVAILABLE','code':safe_error(error),'frames':frames}),flush=True)


def record(product,state=None,*,error=None):
    with product.db.tx() as s:
        row=s.get(Meta,'worker_health')
        value=json.loads(row.value) if row else {}
        if value.get('pid')!=os.getpid() or state=='STARTING':value={'consecutive_errors':0,'state':'STARTING'}
        value.update(at=now().isoformat(),pid=os.getpid())
        if state:
            value['state']=state
            if state=='WORKING':value['cycle_started_at']=value['at']
            if state=='ERROR':
                value['consecutive_errors']=value.get('consecutive_errors',0)+1
                value['last_error']=error;value['last_error_at']=value['at']
            elif state in ('OK','NOT_CONFIGURED'):
                value['consecutive_errors']=0;value['last_success_at']=value['at'];value['last_error']=None
        if row:row.value=json.dumps(value)
        else:s.add(Meta(key='worker_health',value=json.dumps(value)))


def status(session):
    row=session.get(Meta,'worker_health')
    if not row:return {'process':'UNKNOWN','dispatch':'UNKNOWN','consecutive_errors':0}
    try:
        from datetime import datetime
        value=json.loads(row.value)
        fresh=(now()-aware(datetime.fromisoformat(value['at']))).total_seconds()<90
        dispatch=value.get('state','UNKNOWN')
        if value.get('consecutive_errors',0):dispatch='ERROR'
        elif dispatch=='WORKING':
            progress=datetime.fromisoformat(value['cycle_started_at'])
            heartbeat=session.get(Meta,'worker_heartbeat')
            if heartbeat:
                beat=json.loads(heartbeat.value)
                if beat.get('pid')==value.get('pid'):progress=max(aware(progress),aware(datetime.fromisoformat(beat['at'])))
            if (now()-aware(progress)).total_seconds()>=90:dispatch='STALLED'
        return {**value,'process':'RESPONDING' if fresh else 'STALE',
                'dispatch':dispatch if fresh else 'STALE'}
    except (ValueError,KeyError,TypeError):return {'process':'UNKNOWN','dispatch':'UNKNOWN','consecutive_errors':0}


async def pulse(product):
    while True:
        await asyncio.sleep(20)
        try:record(product)
        except Exception as error:log_error(error)
