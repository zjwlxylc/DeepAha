"""Invitation admission and account administration; no domain approval authority."""
import re
import secrets
from datetime import timedelta
from sqlalchemy import select, func
from .auth import ROLES, aware, digest, password_hash, verify_password
from .errors import Problem
from .models import Account, Audit, Invitation, InvitationRedemption, LoginAttempt, LoginSession, PasswordReset, now

NOTICE_VERSION='beta-access-v1'
INVITATION_CODE_SPACE=10000
ACCESS_ACTIONS={'INVITE_CREATE','INVITE_REVOKE','INVITE_REDEEM','ADMIN_ACCOUNT','ADMIN_REVOKE_SESSIONS','ADMIN_RESET_ISSUE','ACCESS_PASSWORD_RESET','ACCESS_PASSWORD_CHANGE','ACCESS_ADMIN_BOOTSTRAP','ACCESS_ROLE_MIGRATION','ACCESS_ROLE_ROLLBACK','ACCESS_OPERATOR_GRANT'}


def _revoke_sessions(s, account_id):
    for row in s.scalars(select(LoginSession).where(LoginSession.account_id==account_id)):row.revoked=True


def _invalidate_resets(s, account_id):
    for row in s.scalars(select(PasswordReset).where(PasswordReset.account_id==account_id)):row.used=True


def _invitation(row):
    status='REVOKED' if row.revoked else 'EXPIRED' if aware(row.expires_at)<=now() else 'EXHAUSTED' if row.used_count>=row.max_uses else 'ACTIVE'
    return {'id':row.id,'label':row.label,'max_uses':row.max_uses,'used_count':row.used_count,'expires_at':aware(row.expires_at).isoformat(),'created_at':aware(row.created_at).isoformat(),'created_by':row.created_by,'status':status}


class AccessMixin:
    def migrate_access_roles(self):
        """Explicit backup-first migration; no passwords or business roles removed."""
        changes=[]
        with self.db.tx() as s:
            for account in s.scalars(select(Account).order_by(Account.id)):
                if 'admin' not in account.roles:continue
                before=list(account.roles)
                after=list(dict.fromkeys([r for r in before if r!='admin']+['operator']))
                account.roles=after
                _revoke_sessions(s,account.id);_invalidate_resets(s,account.id)
                self._audit(s,'SYSTEM_CLI','ACCESS_ROLE_MIGRATION',account.id,'合并账号管理权限到维护员；密码未变更')
                changes.append({'id':account.id,'before':before,'after':after})
        return {'migrated_accounts':len(changes),'changes':changes}

    def restore_access_roles(self,changes):
        """Host-only compensation for a failed deployment, with concurrency guard."""
        with self.db.tx() as s:
            for change in changes:
                account=s.get(Account,change['id'])
                if not account or account.roles!=change['after']:
                    raise Problem('账号角色已发生后续变更，停止自动回退',409,'ROLE_ROLLBACK_CONFLICT')
                account.roles=change['before'];_revoke_sessions(s,account.id);_invalidate_resets(s,account.id)
                self._audit(s,'SYSTEM_CLI','ACCESS_ROLE_ROLLBACK',account.id,'发布失败恢复迁移前角色；密码未变更')
        return {'restored_accounts':len(changes)}

    def _access_limit(self,s,scope,ip,maximum=20):
        key=digest('access|'+scope+'|'+ip)
        row=s.get(LoginAttempt,key)
        if row and now()-aware(row.since)>timedelta(minutes=15):s.delete(row);s.flush();row=None
        if row and row.count>=maximum:raise Problem('尝试次数过多，请15分钟后再试',429,'RATE_LIMITED')
        if not row:row=LoginAttempt(key=key,count=0);s.add(row)
        row.count+=1

    def create_invitations(self,*,actor,label,count=1,max_uses=1,expires_days=7):
        if not label.strip() or len(label)>120 or not 1<=count<=50 or not 1<=max_uses<=1000 or not 1<=expires_days<=90:raise Problem('邀请码设置不正确')
        result=[]
        with self.db.tx() as s:
            self._account(s,actor,'operator')
            occupied=set(s.scalars(select(Invitation.code_hash)))
            available=[f'{n:04d}' for n in range(INVITATION_CODE_SPACE) if digest(f'{n:04d}') not in occupied]
            if count>len(available):raise Problem('四位邀请码已分配完，请联系维护员处理',409,'INVITE_CODES_EXHAUSTED')
            for code in secrets.SystemRandom().sample(available,count):
                row=Invitation(code_hash=digest(code),label=label.strip(),max_uses=max_uses,expires_at=now()+timedelta(days=expires_days),created_by=actor)
                s.add(row);s.flush()
                self._audit(s,actor,'INVITE_CREATE',row.id,f'名额={max_uses};有效天数={expires_days}')
                result.append({**_invitation(row),'code':code})
        return {'items':result}

    def list_invitations(self,*,actor,offset=0,limit=30):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            total=s.scalar(select(func.count()).select_from(Invitation))
            rows=s.scalars(select(Invitation).order_by(Invitation.created_at.desc(),Invitation.id).offset(offset).limit(limit))
            return {'total':total,'items':[_invitation(r) for r in rows]}

    def revoke_invitation(self,id,*,actor):
        with self.db.tx() as s:
            self._account(s,actor,'operator');row=s.get(Invitation,id)
            if not row:raise Problem('邀请码不存在',404)
            row.revoked=True;self._audit(s,actor,'INVITE_REVOKE',id,'停止新注册，不影响已注册账号')
        return {'revoked':True}

    def register_invited(self,username,password,code,*,accepted,ip='local'):
        # Commit the attempt even when validation fails; never commit partial admission.
        with self.db.tx() as s:self._access_limit(s,'register',ip)
        if not accepted:raise Problem('请先阅读并确认体验说明')
        if not re.fullmatch(r'[a-zA-Z0-9_.@\-]{3,80}',username):raise Problem('账号格式不正确')
        with self.db.tx() as s:
            row=s.scalar(select(Invitation).where(Invitation.code_hash==digest(code.strip())))
            if not row or _invitation(row)['status']!='ACTIVE':raise Problem('邀请码无效、已过期或名额已用完，请联系邀请人',400,'INVITE_UNAVAILABLE')
            if s.scalar(select(Account).where(Account.username==username)):raise Problem('账号已存在，请更换账号或登录',409,'ACCOUNT_EXISTS')
            a=Account(username=username,password_hash=password_hash(password),roles=['user'])
            s.add(a);s.flush();row.used_count+=1
            s.add(InvitationRedemption(account_id=a.id,invitation_id=row.id,notice_version=NOTICE_VERSION))
            self._audit(s,username,'INVITE_REDEEM',row.id,'受邀注册；'+NOTICE_VERSION)
            return {'id':a.id,'username':username,'roles':['user']}

    def list_accounts(self,*,actor,q='',offset=0,limit=30):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            cond=Account.username.contains(q,autoescape=True)
            total=s.scalar(select(func.count()).select_from(Account).where(cond))
            rows=s.execute(select(Account,InvitationRedemption,Invitation).outerjoin(InvitationRedemption,Account.id==InvitationRedemption.account_id).outerjoin(Invitation,Invitation.id==InvitationRedemption.invitation_id).where(cond).order_by(Account.created_at.desc(),Account.id).offset(offset).limit(limit))
            return {'total':total,'items':[{'id':a.id,'username':a.username,'roles':a.roles,'active':a.active,'created_at':aware(a.created_at).isoformat(),'invitation_id':i.id if i else None,'cohort':i.label if i else '已有账号 / 人工开通','notice_version':r.notice_version if r else None} for a,r,i in rows]}

    def update_account(self,id,*,actor,active,roles,reason):
        if not roles or set(roles)-ROLES or not reason.strip() or len(reason)>500:raise Problem('角色和操作原因不能为空')
        with self.db.tx() as s:
            admin=self._account(s,actor,'operator');a=s.get(Account,id)
            if not a:raise Problem('账号不存在',404)
            if a.id==admin.id:raise Problem('不能通过管理页面修改自己的角色或状态',409,'SELF_CHANGE_FORBIDDEN')
            if 'operator' in a.roles and a.active and (not active or 'operator' not in roles):
                others=[x for x in s.scalars(select(Account).where(Account.active.is_(True),Account.id!=a.id)) if 'operator' in x.roles]
                if not others:raise Problem('必须保留至少一名活跃维护员',409,'LAST_OPERATOR')
            a.active=active;a.roles=list(dict.fromkeys(roles));_revoke_sessions(s,a.id);_invalidate_resets(s,a.id)
            self._audit(s,actor,'ADMIN_ACCOUNT',id,f'active={active};roles={",".join(a.roles)};原因={reason.strip()}')
        return {'updated':True}

    def revoke_user_sessions(self,id,*,actor,reason):
        with self.db.tx() as s:
            self._account(s,actor,'operator')
            if not s.get(Account,id):raise Problem('账号不存在',404)
            _revoke_sessions(s,id);self._audit(s,actor,'ADMIN_REVOKE_SESSIONS',id,reason)
        return {'revoked':True}

    def issue_password_reset(self,id,*,actor,reason):
        with self.db.tx() as s:
            admin=self._account(s,actor,'operator');a=s.get(Account,id)
            if not a or not a.active:raise Problem('账号不存在或已停用',404)
            if admin.id==a.id:raise Problem('请在账号安全页用旧密码修改自己的密码',409)
            _invalidate_resets(s,id)
            code=secrets.token_urlsafe(32);expires=now()+timedelta(minutes=30)
            s.add(PasswordReset(token_hash=digest(code),account_id=id,expires_at=expires))
            self._audit(s,actor,'ADMIN_RESET_ISSUE',id,reason)
        return {'code':code,'expires_at':expires.isoformat()}

    def reset_password(self,code,password,*,ip='local'):
        with self.db.tx() as s:self._access_limit(s,'reset',ip)
        with self.db.tx() as s:
            row=s.get(PasswordReset,digest(code.strip()))
            if not row or row.used or aware(row.expires_at)<=now():raise Problem('重置码无效或已过期',400,'RESET_UNAVAILABLE')
            a=s.get(Account,row.account_id)
            if not a or not a.active:raise Problem('重置码无效或已过期',400,'RESET_UNAVAILABLE')
            a.password_hash=password_hash(password);_invalidate_resets(s,a.id);_revoke_sessions(s,a.id)
            self._audit(s,a.username,'ACCESS_PASSWORD_RESET',a.id,'已重置密码并撤销全部会话')
        return {'reset':True}

    def change_password(self,old_password,new_password,*,actor):
        with self.db.tx() as s:self._access_limit(s,'password',actor,8)
        with self.db.tx() as s:
            a=self._account(s,actor)
            if not verify_password(old_password,a.password_hash):raise Problem('原密码不正确',400)
            a.password_hash=password_hash(new_password);_revoke_sessions(s,a.id);_invalidate_resets(s,a.id)
            self._audit(s,actor,'ACCESS_PASSWORD_CHANGE',a.id,'用户修改密码并撤销全部会话')
        return {'changed':True}

    def access_audit(self,*,actor,offset=0,limit=30):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            rows=s.scalars(select(Audit).where(Audit.action.in_(ACCESS_ACTIONS)).order_by(Audit.created_at.desc(),Audit.id).offset(offset).limit(limit))
            return {'items':[{'action':r.action,'actor':r.actor,'target':r.target,'summary':r.summary,'created_at':aware(r.created_at).isoformat()} for r in rows]}
