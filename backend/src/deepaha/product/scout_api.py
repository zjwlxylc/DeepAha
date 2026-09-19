"""Same-origin authenticated file submission. No independent importer account DB."""
import asyncio
from pathlib import Path
from urllib.parse import quote
from fastapi import Request, Response, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

class CommitInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    preview_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    selected_ids:list[str]=Field(max_length=2000)
    request_key:str=Field(min_length=1,max_length=128)

class ApprovalInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    approval_version:str=Field(pattern=r'^[0-9a-f]{64}$')
    binding_version:StrictInt=Field(ge=0)
    name:str=Field(min_length=1,max_length=300)
    url:str=Field(min_length=1,max_length=3000)
    tier:str=Field(max_length=40)
    reason:str=Field(min_length=1,max_length=1000)
    request_key:str=Field(min_length=1,max_length=128)
    brief_id:str|None=Field(default=None,max_length=64)
    allowed_hosts:list[str]=Field(default_factory=list,max_length=20)
    enabled:StrictBool=False
    existing_source_id:str|None=Field(default=None,max_length=36)
    expected_policy_version:StrictInt|None=Field(default=None,ge=0)


def mount_scout(app, product, user):
    p=product
    @app.get('/api/manage/scout/capabilities')
    def capabilities(req:Request):
        return p.scout_capabilities(actor=user(req,'operator'))
    @app.post('/api/manage/scout/previews')
    async def upload(req:Request, filename:str=Query(max_length=200)):
        actor=user(req,'operator',True)
        return await asyncio.to_thread(p.scout_prepare, await req.body(), filename, actor=actor)
    @app.get('/api/manage/scout/batches')
    def batches(req:Request, offset:int=Query(0,ge=0), limit:int=Query(20,ge=1,le=50)):
        return p.scout_batches(actor=user(req,'operator'),offset=offset,limit=limit)
    @app.get('/api/manage/scout/batches/{id}')
    def batch(id:str,req:Request):
        return p.scout_batch(id,actor=user(req,'operator'))
    @app.get('/api/manage/scout/batches/{id}/candidates')
    def candidates(id:str,req:Request,q:str=Query('',max_length=300),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=50)):
        return p.scout_items(id,actor=user(req,'operator'),q=q,offset=offset,limit=limit)
    @app.get('/api/manage/scout/batches/{id}/candidates/{candidate}')
    def candidate_detail(id:str,candidate:str,req:Request):
        return p.scout_candidate_detail(id,candidate,actor=user(req,'operator'))
    @app.post('/api/manage/scout/batches/{id}/receive')
    def receive(id:str,data:CommitInput,req:Request):
        return p.scout_commit(id,**data.model_dump(),actor=user(req,'operator',True))
    @app.get('/api/manage/scout/batches/{id}/receipt')
    def receipt(id:str,req:Request):
        return p.scout_receipt(id,actor=user(req,'operator'))
    @app.get('/api/manage/scout/batches/{id}/feedback')
    def feedback(id:str,req:Request,res:Response):
        data=p.scout_feedback(id,actor=user(req,'operator'))
        res.headers['Content-Disposition']='attachment; filename="DeepAha_ScoutFeedback_'+id+'.json"'
        return data
    @app.get('/api/manage/scout/batches/{id}/file')
    def file(id:str,req:Request,name:str=Query(max_length=1600)):
        raw=p.scout_file(id,name,actor=user(req,'operator'))
        return Response(raw,media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(Path(name).name)})
    @app.post('/api/manage/scout/observations/{id}/approve')
    def approve(id:str,data:ApprovalInput,req:Request):
        return p.scout_approve(id,**data.model_dump(),actor=user(req,'operator',True))
