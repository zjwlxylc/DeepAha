"""Versioned, additive endpoints; legacy response shapes remain unchanged."""
from typing import Literal
from fastapi import Request, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictBool

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class ProfilePatch(Strict):
    expected_version:StrictInt=Field(ge=0)
    changes:dict
class ItemInput(Strict):
    text:str=Field(min_length=1,max_length=500)
    request_key:str=Field(min_length=1,max_length=128)
    field_id:str|None=Field(default=None,max_length=128)
class ItemPatch(Strict):
    expected_version:StrictInt=Field(ge=1)
    text:str|None=Field(default=None,min_length=1,max_length=500)
    done:StrictBool|None=None
class ReadInput(Strict):ids:list[str]=Field(max_length=100)

def mount_experience(app,p,user):
    @app.get('/api/me/action-board')
    def board(req:Request,status:Literal['','SAVED','PREPARING','APPLIED','WAITING','COMPLETED','DISMISSED']='',offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):
        return p.my_actions(actor=user(req),offset=offset,limit=limit,_envelope=True,status=status)
    @app.get('/api/me/notification-list')
    def notice_list(req:Request,unread:bool=False,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):
        return p.notifications(actor=user(req),offset=offset,limit=limit,unread=unread,_envelope=True)

    @app.get('/api/me/profile-state')
    def state(req:Request):return p.profile_state(actor=user(req))
    @app.patch('/api/me/profile')
    def profile(data:ProfilePatch,req:Request):return p.patch_profile(data.changes,data.expected_version,actor=user(req,write=True))
    @app.get('/api/manage/source-search')
    def sources(req:Request,q:str=Query('',max_length=300),enabled:bool|None=None,health:Literal['','ISSUES','NEVER','OK']='',offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):
        return p.search_sources(actor=user(req,'operator'),q=q,enabled=enabled,health=health,offset=offset,limit=limit)
    @app.get('/api/manage/sources/{id}')
    def source(id:str,req:Request):return p.source_detail(id,actor=user(req,'operator'))
    @app.get('/api/manage/task-search')
    def tasks(req:Request,q:str=Query('',max_length=300),status:Literal['','QUEUED','RUNNING','RECOVERY_QUEUED','NEEDS_RECOVERY','FAILED','READY','CANCELLED']='',source_id:str=Query('',max_length=64),offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):
        return p.search_tasks(actor=user(req,'operator'),q=q,status=status,source_id=source_id,offset=offset,limit=limit)
    @app.get('/api/me/actions/{target_id}/items')
    def items(target_id:str,req:Request):return p.preparation_items(target_id,actor=user(req))
    @app.post('/api/me/actions/{target_id}/items')
    def add(target_id:str,data:ItemInput,req:Request):return p.add_preparation_item(target_id,actor=user(req,write=True),**data.model_dump())
    @app.patch('/api/me/actions/{target_id}/items/{id}')
    def edit(target_id:str,id:str,data:ItemPatch,req:Request):return p.update_preparation_item(target_id,id,actor=user(req,write=True),**data.model_dump())
    @app.delete('/api/me/actions/{target_id}/items/{id}')
    def remove(target_id:str,id:str,req:Request,expected_version:int=Query(ge=1)):return p.update_preparation_item(target_id,id,actor=user(req,write=True),expected_version=expected_version,remove=True)
    @app.post('/api/me/notifications/read')
    def mark(data:ReadInput,req:Request):return p.mark_notifications(data.ids,actor=user(req,write=True))

class PolicyInput(Strict):
    expected_version:StrictInt=Field(ge=0)
    mode:Literal['SERIAL','PARALLEL']='SERIAL'
    max_concurrent:StrictInt=Field(default=1,ge=1,le=4)
    queue_limit:StrictInt=Field(default=20,ge=1,le=1000)
    task_budget_seconds:StrictInt=Field(default=1200,ge=60,le=1800)
    new_dispatch_enabled:StrictBool=True
    domain_limit:StrictInt=Field(default=1,ge=1,le=4)
class RemoteEnded(Strict):
    terminal_confirmed:Literal[True]
    reason:str=Field(min_length=1,max_length=500)

def mount_dispatch(app,p,user,registry):
    from .errors import Problem
    @app.get('/api/manage/execution-policies')
    def policies(req:Request):
        actor=user(req,'operator');bindings=registry.public()
        return {**p.execution_policies(actor=actor,binding_refs=[x['id'] for x in bindings]),'bindings':bindings}
    @app.put('/api/manage/execution-policies/{ref}')
    def save(ref:str,data:PolicyInput,req:Request):
        actor=user(req,'operator',True)
        if ref not in registry.definitions():raise Problem('宿主未登记该连接',404)
        return p.set_execution_policy(ref,actor=actor,**data.model_dump())
    @app.post('/api/manage/execution-policies/{ref}/inspect')
    async def inspect(ref:str,req:Request):
        actor=user(req,'operator',True);factory=registry.factory(ref)
        if not factory:raise Problem('连接未启用或宿主凭据尚未配置',409,'NOT_CONFIGURED')
        client=None
        try:
            client=factory();release=await client.inspect_release()
            p.observe_binding(ref,registry.fingerprint(ref,release),release,actor=actor)
            return {'inspected':True,'investigation_sent':False,'policies':p.execution_policies(actor=actor)}
        except Problem:raise
        except Exception:raise Problem('无法读取发布绑定，请检查宿主连接配置',503,'BINDING_INSPECTION_FAILED') from None
        finally:
            if client:await client.aclose()
    @app.post('/api/manage/tasks/{id}/remote-ended')
    def release(id:str,data:RemoteEnded,req:Request):return p.confirm_remote_terminal(id,data.reason,actor=user(req,'operator',True))
