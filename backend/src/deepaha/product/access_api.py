"""Same-origin access administration; all management writes require CSRF and admin."""
from typing import Literal
from fastapi import Request, Query
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class InvitationInput(Strict):
    label:str=Field(min_length=1,max_length=120)
    count:int=Field(default=1,ge=1,le=50)
    max_uses:int=Field(default=1,ge=1,le=1000)
    expires_days:int=Field(default=7,ge=1,le=90)
class Reason(Strict):reason:str=Field(min_length=1,max_length=500,pattern=r'\S')
class AccountUpdate(Reason):
    active:bool
    roles:list[Literal['user','reviewer','operator','admin']]=Field(min_length=1,max_length=4)
class ResetInput(Strict):
    code:str=Field(min_length=1,max_length=128)
    password:str=Field(min_length=12,max_length=256)
class PasswordInput(Strict):
    old_password:str=Field(min_length=1,max_length=256)
    new_password:str=Field(min_length=12,max_length=256)

def mount_access(app,p,user):
    @app.get('/api/admin/invitations')
    def invitations(req:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100)):
        return p.list_invitations(actor=user(req,'admin'),offset=offset,limit=limit)
    @app.post('/api/admin/invitations')
    def create(data:InvitationInput,req:Request):return p.create_invitations(actor=user(req,'admin',True),**data.model_dump())
    @app.post('/api/admin/invitations/{id}/revoke')
    def revoke(id:str,req:Request):return p.revoke_invitation(id,actor=user(req,'admin',True))
    @app.get('/api/admin/users')
    def users(req:Request,q:str=Query('',max_length=80),offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100)):
        return p.list_accounts(actor=user(req,'admin'),q=q,offset=offset,limit=limit)
    @app.patch('/api/admin/users/{id}')
    def update(id:str,data:AccountUpdate,req:Request):return p.update_account(id,actor=user(req,'admin',True),**data.model_dump())
    @app.post('/api/admin/users/{id}/revoke-sessions')
    def sessions(id:str,data:Reason,req:Request):return p.revoke_user_sessions(id,actor=user(req,'admin',True),reason=data.reason)
    @app.post('/api/admin/users/{id}/password-reset')
    def issue(id:str,data:Reason,req:Request):return p.issue_password_reset(id,actor=user(req,'admin',True),reason=data.reason)
    @app.get('/api/admin/audit')
    def audit(req:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100)):
        return p.access_audit(actor=user(req,'admin'),offset=offset,limit=limit)
    @app.post('/api/auth/reset-password')
    def reset(data:ResetInput,req:Request):return p.reset_password(data.code,data.password,ip=req.client.host if req.client else 'unknown')
    @app.post('/api/auth/change-password')
    def password(data:PasswordInput,req:Request):return p.change_password(data.old_password,data.new_password,actor=user(req,write=True))
