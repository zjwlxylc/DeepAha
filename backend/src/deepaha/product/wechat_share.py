"""Server-side WeChat ticket cache and JS-SDK signatures; fixed outbound endpoints.

Secrets are environment-only. The public API returns a signature, never a ticket
or access token. The SDK is loaded on isolated public share pages, not the SPA.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import time
import httpx
from .errors import Problem

API='https://api.weixin.qq.com'


@contextmanager
def file_lock(path,timeout=25):
    if path.is_symlink():raise Problem('微信缓存锁异常',503,'WECHAT_CACHE_FAILED')
    with path.open('a+b') as h:
        if h.tell()==0:h.write(b'0');h.flush()
        start=time.monotonic()
        while True:
            try:
                h.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(h.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except (OSError,BlockingIOError):
                if time.monotonic()-start>timeout:raise Problem('分享配置正在更新，请稍后重试',503,'WECHAT_BUSY')
                time.sleep(.05)
        try:yield
        finally:
            h.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(h.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(h.fileno(),fcntl.LOCK_UN)


def signature(ticket,nonce,timestamp,url):
    return hashlib.sha1(f'jsapi_ticket={ticket}&noncestr={nonce}&timestamp={timestamp}&url={url}'.encode()).hexdigest()


class WeChatShare:
    def __init__(self,cache_dir,transport=None,clock=time.time):
        self.cache_dir=Path(cache_dir);self.transport=transport;self.clock=clock
        self.lock=threading.RLock();self.rates={}

    def credentials(self):
        app=os.getenv('DEEPAHA_WECHAT_APP_ID','').strip();secret=os.getenv('DEEPAHA_WECHAT_APP_SECRET','').strip()
        return app,secret

    def status(self):
        app,secret=self.credentials()
        return {'credentials_configured':bool(app and secret),'app_id':app if re.fullmatch(r'wx[A-Za-z0-9]{6,48}',app) else '',
                'secret_configured':bool(secret),'live_wechat_verified':False,
                'sdk':'https://res.wx.qq.com/open/js/jweixin-1.6.0.js',
                'required':'宿主配置可用公众号权限、JS接口安全域名与接口IP白名单，并在真实微信验证'}

    def _save(self,path,data):
        fd,tmp=tempfile.mkstemp(prefix='.cache-',dir=self.cache_dir)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as h:
                json.dump(data,h);h.flush();os.fsync(h.fileno())
            os.chmod(tmp,0o600);os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)

    def ticket(self,app,secret):
        # Fingerprint invalidates cache on rotation without persisting the secret.
        fingerprint=hashlib.sha256((app+'\0'+secret).encode()).hexdigest()
        if self.cache_dir.is_symlink():raise Problem('微信缓存目录不正确',503,'WECHAT_CACHE_FAILED')
        self.cache_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(self.cache_dir,0o700)
        path=self.cache_dir/(fingerprint+'.json')
        with self.lock,file_lock(self.cache_dir/'ticket.lock'):
            t=self.clock();cached={}
            if path.exists():
                if path.is_symlink() or path.stat().st_size>65536:raise Problem('微信缓存异常',503,'WECHAT_CACHE_FAILED')
                try:cached=json.loads(path.read_text(encoding='utf-8'))
                except (ValueError,OSError):cached={}
            if cached.get('ticket') and cached.get('expires_at',0)>t+120:return cached['ticket']
            if cached.get('retry_after',0)>t:raise Problem('微信接口暂不可用，请稍后重试',503,'WECHAT_UNAVAILABLE')
            try:
                with httpx.Client(timeout=8,follow_redirects=False,transport=self.transport,trust_env=False) as client:
                    token=cached.get('token') if cached.get('token_expires_at',0)>t+120 else None
                    if not token:
                        r=client.post(API+'/cgi-bin/stable_token',json={'grant_type':'client_credential','appid':app,'secret':secret,'force_refresh':False})
                        r.raise_for_status();data=r.json()
                        if data.get('errcode',0)!=0 or not isinstance(data.get('access_token'),str):raise ValueError()
                        token=data['access_token'];cached['token']=token;cached['token_expires_at']=t+max(60,min(7200,int(data['expires_in'])))
                    r=client.get(API+'/cgi-bin/ticket/getticket',params={'access_token':token,'type':'jsapi'})
                    r.raise_for_status();data=r.json()
                    if data.get('errcode',0)!=0 or not isinstance(data.get('ticket'),str) or not data['ticket']:raise ValueError()
                    cached.update(ticket=data['ticket'],expires_at=t+max(60,min(7200,int(data['expires_in']))),retry_after=0)
                    self._save(path,cached)
                    return cached['ticket']
            except (httpx.HTTPError,ValueError,KeyError,TypeError,OSError):
                # Never emit exception text, upstream body or token-bearing request URL.
                cached.update(retry_after=t+60)
                try:self._save(path,cached)
                except OSError:pass
                raise Problem('微信分享配置未就绪，请核对账号权限、域名和IP白名单',503,'WECHAT_UNAVAILABLE') from None

    def sign(self,url,ip):
        app,secret=self.credentials()
        if not app or not secret:return {'enabled':False,'state':'NOT_CONFIGURED'}
        if not re.fullmatch(r'wx[A-Za-z0-9]{6,48}',app) or len(secret)>256:raise Problem('微信服务端配置不正确',503,'WECHAT_NOT_CONFIGURED')
        with self.lock:
            t=self.clock();bucket=int(t//60)
            self.rates={k:v for k,v in self.rates.items() if v[0]==bucket}
            if len(self.rates)>=1000 and ip not in self.rates:raise Problem('请求较多，请稍候',429,'SHARE_RATE_LIMIT')
            _,count=self.rates.get(ip,(bucket,0))
            if count>=30:raise Problem('分享配置请求过于频繁',429,'SHARE_RATE_LIMIT')
            self.rates[ip]=(bucket,count+1)
        ticket=self.ticket(app,secret);nonce=secrets.token_hex(16);timestamp=int(self.clock())
        return {'enabled':True,'appId':app,'nonceStr':nonce,'timestamp':timestamp,
                'signature':signature(ticket,nonce,timestamp,url),
                'jsApiList':['updateAppMessageShareData','updateTimelineShareData']}
