import hashlib
import hmac
import secrets
from datetime import timedelta,timezone
from sqlalchemy import select
from .models import Account, LoginSession, LoginAttempt, PasswordReset, Audit, now
from .errors import Problem

ROLES={'user','reviewer','operator'}
def has_role(roles,required):
    return required in roles or (required=='reviewer' and 'operator' in roles)
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def aware(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def password_hash(password):
    if not 4<=len(password)<=256:raise Problem('密码须为4至256个字符')
    salt=secrets.token_hex(16)
    key=hashlib.scrypt(password.encode(),salt=salt.encode(),n=32768,r=8,p=1,maxmem=67108864).hex()
    return 'scrypt$32768$'+salt+'$'+key

def verify_password(password,stored):
    try:
        _,n,salt,key=stored.split('$')
        got=hashlib.scrypt(password.encode(),salt=salt.encode(),n=int(n),r=8,p=1,maxmem=67108864).hex()
        return hmac.compare_digest(got,key)
    except (ValueError,TypeError):return False

class AuthMixin:
    def _account(self,s,actor,role=None):
        a=s.scalar(select(Account).where(Account.username==actor,Account.active.is_(True)))
        if not a:raise Problem('请重新登录',401,'AUTH_REQUIRED')
        if role and not has_role(a.roles,role):raise Problem('没有执行此操作的权限',403,'FORBIDDEN')
        return a
    def create_account(self,username,password,roles):
        import re
        if not re.fullmatch(r'[a-zA-Z0-9_.@\-]{3,80}',username):raise Problem('账号格式不正确')
        if not roles or set(roles)-ROLES:raise Problem('角色不正确')
        ph=password_hash(password)
        with self.db.tx() as s:
            if s.scalar(select(Account).where(Account.username==username)):raise Problem('账号已存在',409)
            a=Account(username=username,password_hash=ph,roles=list(dict.fromkeys(roles)))
            s.add(a);s.flush()
            s.add(Audit(actor='SYSTEM_CLI',action='CREATE_ACCOUNT',target=a.id,summary=','.join(roles)))
            return {'id':a.id,'username':a.username,'roles':a.roles}
    def login(self,username,password,ip='local'):
        key=digest(ip+'|'+username.lower())
        failure=False
        with self.db.tx() as s:
            limit=s.get(LoginAttempt,key)
            if limit and now()-aware(limit.since)>timedelta(minutes=15):s.delete(limit);s.flush();limit=None
            if limit and limit.count>=8:raise Problem('尝试次数过多，请15分钟后再试',429,'RATE_LIMITED')
            a=s.scalar(select(Account).where(Account.username==username,Account.active.is_(True)))
            # Dummy work makes unknown usernames less distinguishable.
            ok=verify_password(password,a.password_hash) if a else verify_password(password,'scrypt$32768$'+'0'*32+'$'+'0'*128)
            if not ok:
                if not limit:limit=LoginAttempt(key=key,count=0);s.add(limit)
                limit.count+=1;failure=True
            else:
                if limit:s.delete(limit)
                token=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32)
                s.add(LoginSession(token_hash=digest(token),account_id=a.id,csrf_hash=digest(csrf),expires_at=now()+timedelta(hours=12)))
                result={'token':token,'csrf':csrf,'username':a.username,'roles':a.roles}
        if failure:raise Problem('账号或密码不正确',401,'LOGIN_FAILED')
        return result
    def authenticate(self,token,csrf=None):
        if not token:raise Problem('请先登录',401,'AUTH_REQUIRED')
        with self.db.tx(False) as s:
            se=s.get(LoginSession,digest(token))
            if not se or se.revoked or aware(se.expires_at)<=now():raise Problem('登录已过期',401,'SESSION_EXPIRED')
            a=s.get(Account,se.account_id)
            if not a or not a.active:raise Problem('账号已停用',401)
            if csrf is not None and not hmac.compare_digest(digest(csrf),se.csrf_hash):raise Problem('请求校验失败，请刷新页面',403,'CSRF_FAILED')
            return {'username':a.username,'roles':a.roles,'id':a.id}
    def logout(self,token):
        with self.db.tx() as s:
            r=s.get(LoginSession,digest(token))
            if r:r.revoked=True
    def revoke_account(self,username,active=False):
        with self.db.tx() as s:
            a=s.scalar(select(Account).where(Account.username==username))
            if not a:raise Problem('账号不存在',404)
            a.active=active
            for se in s.scalars(select(LoginSession).where(LoginSession.account_id==a.id)):se.revoked=True
            for reset in s.scalars(select(PasswordReset).where(PasswordReset.account_id==a.id)):reset.used=True
            s.add(Audit(actor='SYSTEM_CLI',action='ACCOUNT_STATUS',target=a.id,summary='active='+str(active)))
