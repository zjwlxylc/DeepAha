"""Operator share configuration, public metadata and content-addressed covers."""
from typing import Literal
from fastapi import Request, Query
from fastapi.responses import HTMLResponse,FileResponse,PlainTextResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from . import sharing
from .errors import Problem

class ShareInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:StrictInt=Field(ge=0)
    origin:str=Field(max_length=300)
    title:str=Field(min_length=1,max_length=80)
    description:str=Field(min_length=1,max_length=220)
    cover:str=Field(max_length=80)
    square:str=Field(max_length=80)
    wechat_enabled:StrictBool=False
    verification_name:str=Field(default='',max_length=120)
    verification_text:str=Field(default='',max_length=256)


def mount_sharing(app,p,settings,user,static):
    from .wechat_share import WeChatShare
    wechat=WeChatShare(settings.data_dir/'private'/'wechat')
    app.state.wechat_share=wechat
    @app.get('/api/manage/sharing')
    def get(req:Request):
        user(req,'operator')
        return {**sharing.get_config(p),'diagnostics':wechat.status()}
    @app.put('/api/manage/sharing')
    def put(data:ShareInput,req:Request):
        return sharing.save_config(p,static,user(req,'operator',True),data.model_dump())
    @app.post('/api/manage/sharing/cover')
    async def upload(req:Request,kind:Literal['wide','square']='wide'):
        actor=user(req,'operator',True)
        result=sharing.store_cover(p,await req.body(),kind)
        with p.db.tx() as s:p._audit(s,actor,'UPLOAD_SHARE_COVER',result['asset'],'公开封面；已清除EXIF并转为JPEG')
        return result
    @app.api_route('/share-assets/{name}',methods=['GET','HEAD'])
    def asset(name:str):
        f=sharing.asset_file(p,static,name)
        if not f.is_file():raise Problem('封面不存在',404)
        return FileResponse(f,media_type='image/jpeg',headers={'Cache-Control':'public, max-age=31536000, immutable' if sharing.ASSET.fullmatch(name) else 'public, max-age=3600'})
    @app.get('/api/share/page')
    def page_info(path:str=Query('/share',max_length=256)):
        value=sharing.metadata(p,settings,path)
        if value is None:raise Problem('此页面不支持公开分享',400)
        return value
    @app.api_route('/share',methods=['GET','HEAD'],response_class=HTMLResponse)
    def share():return sharing.landing(sharing.metadata(p,settings,'/share'))
    @app.api_route('/share/opportunity/{id}',methods=['GET','HEAD'],response_class=HTMLResponse)
    def opportunity(id:str):
        value=sharing.metadata(p,settings,'/share/opportunity/'+id)
        if value is None:raise Problem('公开机会不存在',404)
        return sharing.landing(value)
    @app.get('/api/share/wechat-signature')
    def signature(req:Request,url:str=Query(max_length=2048)):
        config=sharing.get_config(p);clean=sharing.signature_url(url,config)
        # Recheck current publication, even when the SDK cache could still be valid.
        from urllib.parse import urlsplit
        sharing.metadata(p,settings,urlsplit(clean).path)
        if not config['wechat_enabled']:return {'enabled':False,'state':'DISABLED'}
        return wechat.sign(clean,req.client.host if req.client else 'unknown')
    def verification(name):
        if not sharing.VERIFY.fullmatch(name):return None
        c=sharing.get_config(p)
        if name!=c['verification_name']:raise Problem('验证文件不存在',404)
        return PlainTextResponse(c['verification_text'],headers={'Cache-Control':'no-store'})
    return verification
