"""Fixed-term commercial terms. This module never verifies or initiates a payment."""
from datetime import timedelta
import re
from sqlalchemy import select, insert, update, func
from .db import (Store, services, plans, revisions, orders, grants, row, rows, uid)
from .auth import Actor
from .periods import add_months, parse, stamp
from .errors import require, DomainError

CAPABILITIES={'topic_watch','site_watch','inapp_alerts','manual'}


def bounded_text(value, maximum, label, minimum=1):
    require(isinstance(value,str) and minimum<=len(value.strip())<=maximum,f'{label}应为{minimum}至{maximum}字符')
    return value.strip()


def integer(value, low, high, label):
    require(type(value) is int and low<=value<=high,f'{label}应为{low}至{high}的整数')
    return value


def code_value(value):
    require(isinstance(value,str) and re.fullmatch(r'[a-z][a-z0-9_]{1,47}',value),'标识应为2至48位小写字母、数字或下划线')
    return value


class Commerce:
    def __init__(self, store: Store):self.s=store

    def seed(self):
        self.s.assert_ready()
        with self.s.write() as c:
            if c.execute(select(func.count()).select_from(plans)).scalar():return
            definitions=[('topic_watch','主题机会跟踪','按关键词、类别和地区持续检查已发布机会。'),
                         ('inapp_alerts','站内更新提醒','新发现或版本变化进入站内消息；不含短信或微信发送。'),
                         ('site_watch','指定网站跟踪','先核验公开网站，再由维护员接入既有采集任务。')]
            for code,label,description in definitions:
                c.execute(insert(services).values(code=code,version=1,data=dict(code=code,label=label,description=description,capability=code,active=True)))
            for code,name,tier,months,price,topics,sites,hours in [
                ('basic','基础订阅','BASIC',2,2990,3,0,24),
                ('deep','深度订阅','DEEP',12,12900,10,0,6),
                ('custom','定制订阅','CUSTOM',2,None,10,3,6)]:
                data=dict(name=name,description={'basic':'陪你走完一个关键机会窗口','deep':'让全年重要机会持续进入视野','custom':'围绕你指定的公开网站定制跟踪'}[code],
                          tier=tier,months=months,price_cents=price,topic_limit=topics,site_limit=sites,scan_hours=hours,
                          service_codes=['topic_watch','inapp_alerts']+(['site_watch'] if sites else []),sort_order={'basic':10,'deep':20,'custom':30}[code])
                terms=self._terms(c,data)
                c.execute(insert(plans).values(code=code,version=1,status='DRAFT'))
                c.execute(insert(revisions).values(code=code,version=1,terms=terms,created_at=self.s.time()))
            self.s.audit(c,'system:init','SEED_DRAFT_CATALOG','catalog')

    def _terms(self,c,data):
        d=dict(data)
        allowed={'name','description','tier','months','price_cents','topic_limit','site_limit','scan_hours','site_scan_hours','service_codes','sort_order','services','scope'}
        require(not set(d)-allowed,'套餐包含未知设置')
        out=dict(name=bounded_text(d.get('name'),80,'套餐名称'),description=bounded_text(d.get('description',''),1600,'套餐说明',0),
                 tier=d.get('tier'),months=integer(d.get('months'),1,36,'自然月时长'),
                 topic_limit=integer(d.get('topic_limit'),0,50,'主题名额'),site_limit=integer(d.get('site_limit'),0,20,'网站名额'),
                 scan_hours=integer(d.get('scan_hours'),6,168,'检查小时数'),site_scan_hours=integer(d.get('site_scan_hours',24),24,720,'网站调查间隔'),sort_order=integer(d.get('sort_order',50),0,999,'排序'))
        require(out['tier'] in ('BASIC','DEEP','CUSTOM'),'订阅类型不正确')
        price=d.get('price_cents')
        if out['tier']=='CUSTOM':require(price is None,'定制套餐按单报价，公开目录不要设置虚构价格')
        else:integer(price,1,10000000,'价格（分）')
        out['price_cents']=price
        keys=d.get('service_codes',[])
        require(isinstance(keys,list) and 1<=len(keys)<=20 and len(set(keys))==len(keys),'请选择1至20个不重复的服务项目')
        selected=[]
        for key in keys:
            rec=row(c,select(services).where(services.c.code==key))
            require(rec and rec['data']['active'],'所选服务项目不存在或已停用')
            selected.append({**rec['data'],'version':rec['version']})
        caps={x['capability'] for x in selected}
        require(not out['topic_limit'] or {'topic_watch','inapp_alerts'}<=caps,'主题跟踪需同时包含主题服务和站内提醒')
        require(not out['site_limit'] or 'site_watch' in caps,'网站名额需包含指定网站跟踪服务')
        require(out['tier']=='CUSTOM' or not out['site_limit'],'指定网站名额仅在定制类型中提供')
        out.update(service_codes=list(keys),services=selected)
        return out

    def list_services(self):
        with self.s.read() as c:return [{**r['data'],'version':r['version']} for r in rows(c,select(services).order_by(services.c.code))]

    def save_service(self,a:Actor,data,expected_version=None):
        a.need('operator');code=code_value(data.get('code'))
        capability=data.get('capability','manual')
        require(capability in CAPABILITIES,'自动能力不受支持；自定义服务请使用人工履约类型')
        require(type(data.get('active',True)) is bool,'启用状态必须是布尔值')
        clean=dict(code=code,label=bounded_text(data.get('label'),80,'服务名称'),description=bounded_text(data.get('description',''),1200,'服务说明',0),capability=capability,active=data.get('active',True))
        with self.s.write() as c:
            old=row(c,select(services).where(services.c.code==code))
            if old:
                require(expected_version==old['version'],'服务项目已变化，请刷新',409,'STALE_VERSION')
                require(old['data']['capability']==capability,'已建服务项目不能改换自动能力；请新建项目')
                version=old['version']+1
                c.execute(update(services).where(services.c.code==code).values(data=clean,version=version))
            else:
                require(expected_version is None,'服务项目不存在',404)
                version=1;c.execute(insert(services).values(code=code,data=clean,version=version))
            self.s.audit(c,a.name,'SAVE_SERVICE',code,{'version':version})
            return {**clean,'version':version}

    def _plan(self,c,code):
        p=row(c,select(plans).where(plans.c.code==code));require(p,'套餐不存在',404)
        r=row(c,select(revisions).where(revisions.c.code==code,revisions.c.version==p['version']))
        return {**p,'terms':r['terms']}

    def plan(self,code,admin=False):
        with self.s.read() as c:
            p=self._plan(c,code)
            require(admin or p['status']=='PUBLISHED','套餐未上架',404)
            return p

    def list_plans(self,admin=False):
        with self.s.read() as c:
            found=[self._plan(c,code) for code in c.execute(select(plans.c.code)).scalars()]
        return sorted((x for x in found if admin or x['status']=='PUBLISHED'),key=lambda x:(x['terms']['sort_order'],x['code']))

    def create_plan(self,a:Actor,code,data):
        a.need('operator');code_value(code)
        with self.s.write() as c:
            require(not row(c,select(plans).where(plans.c.code==code)),'套餐标识已存在',409)
            terms=self._terms(c,data)
            c.execute(insert(plans).values(code=code,version=1,status='DRAFT'))
            c.execute(insert(revisions).values(code=code,version=1,terms=terms,created_at=self.s.time()))
            self.s.audit(c,a.name,'CREATE_PLAN',code)
            return self._plan(c,code)

    def revise_plan(self,a:Actor,code,expected_version,data):
        a.need('operator')
        with self.s.write() as c:
            p=self._plan(c,code);require(p['version']==expected_version,'套餐已变化，请刷新',409,'STALE_VERSION')
            terms=self._terms(c,data);v=p['version']+1
            c.execute(insert(revisions).values(code=code,version=v,terms=terms,created_at=self.s.time()))
            c.execute(update(plans).where(plans.c.code==code).values(version=v))
            self.s.audit(c,a.name,'REVISE_PLAN',code,{'from_version':expected_version,'to_version':v})
            return self._plan(c,code)

    def set_status(self,a:Actor,code,status,expected_version):
        a.need('operator');require(status in ('DRAFT','PUBLISHED','ARCHIVED'),'套餐状态不正确')
        with self.s.write() as c:
            p=self._plan(c,code);require(p['version']==expected_version,'套餐已变化，请刷新',409,'STALE_VERSION')
            c.execute(update(plans).where(plans.c.code==code).values(status=status))
            self.s.audit(c,a.name,'SET_PLAN_STATUS',code,{'status':status})
            return self._plan(c,code)

    def create_order(self,a:Actor,code,version,key,note=''):
        note=bounded_text(note,3000,'需求说明',0)
        with self.s.write() as c:
            def action():
                p=self._plan(c,code)
                require(p['status']=='PUBLISHED','套餐暂不可申请',409)
                require(p['version']==version,'服务内容或价格已变化，请重新确认',409,'STALE_VERSION')
                terms=p['terms'];custom=terms['tier']=='CUSTOM'
                if custom:require(len(note)>=5,'请描述希望跟踪的网站或机会方向')
                pending=c.execute(select(func.count()).select_from(orders).where(orders.c.owner==a.name,orders.c.state.in_(['PENDING','REQUESTED','QUOTED']))).scalar()
                require(pending<5,'待处理申请较多，请先处理现有申请',429,'ORDER_LIMIT')
                out=dict(id=uid(),owner=a.name,plan_code=code,terms={**terms,'plan_version':version},state='REQUESTED' if custom else 'PENDING',version=1,
                         amount_cents=terms['price_cents'],note=note,created_at=self.s.time(),updated_at=self.s.time(),quote_expires=None,settlement_ref=None)
                c.execute(insert(orders).values(**out));self.s.audit(c,a.name,'CREATE_ORDER',out['id'])
                return out
            return self.s.idempotent(c,a.name,'create_order',key,{'code':code,'version':version,'note':note},action)

    def _order(self,c,id):
        out=row(c,select(orders).where(orders.c.id==id));require(out,'服务申请不存在',404)
        return out

    def get_order(self,a:Actor,id):
        with self.s.read() as c:
            out=self._order(c,id);require(out['owner']==a.name or a.has('operator'),'服务申请不存在',404)
            return out

    def list_orders(self,a:Actor,manage=False,limit=100):
        if manage:a.need('operator')
        with self.s.read() as c:
            q=select(orders).order_by(orders.c.created_at.desc(),orders.c.id).limit(min(limit,200))
            if not manage:q=q.where(orders.c.owner==a.name)
            return rows(c,q)

    def quote(self,a:Actor,id,version,amount_cents,months,site_limit,topic_limit,scope,key):
        a.need('operator');integer(amount_cents,1,10000000,'报价（分）');integer(months,1,36,'自然月时长')
        integer(site_limit,1,20,'网站名额');integer(topic_limit,0,50,'主题名额');scope=bounded_text(scope,3000,'定制履约范围',10)
        payload=dict(id=id,version=version,amount=amount_cents,months=months,sites=site_limit,topics=topic_limit,scope=scope)
        with self.s.write() as c:
            def action():
                o=self._order(c,id);require(o['state'] in ('REQUESTED','QUOTED') and o['terms']['tier']=='CUSTOM','当前状态不能报价',409)
                require(o['version']==version,'申请已变化，请刷新',409,'STALE_VERSION')
                capabilities={service['capability'] for service in o['terms']['services']}
                require('site_watch' in capabilities,'此订单未包含指定网站能力，不能只增加网站名额',409,'CAPABILITY_MISMATCH')
                require(not topic_limit or {'topic_watch','inapp_alerts'}.issubset(capabilities),'主题名额需要相应跟踪和提醒能力',409,'CAPABILITY_MISMATCH')
                t={**o['terms'],'price_cents':amount_cents,'months':months,'site_limit':site_limit,'topic_limit':topic_limit,'scope':scope}
                values=dict(terms=t,amount_cents=amount_cents,state='QUOTED',version=version+1,quote_expires=stamp(self.s.clock()+timedelta(days=7)),updated_at=self.s.time())
                c.execute(update(orders).where(orders.c.id==id).values(**values))
                self.s.audit(c,a.name,'QUOTE_CUSTOM_ORDER',id,{'amount_cents':amount_cents})
                self.s.notice(c,o['owner'],'quote:'+id+':'+str(version+1),'定制方案已报价','请核对服务范围、周期和价格后确认。','orders')
                return {**o,**values}
            return self.s.idempotent(c,a.name,'quote',key,payload,action)

    def accept_quote(self,a:Actor,id,version,key):
        with self.s.write() as c:
            def action():
                o=self._order(c,id);require(o['owner']==a.name,'服务申请不存在',404)
                require(o['state']=='QUOTED' and o['version']==version,'报价已变化，请刷新',409,'STALE_VERSION')
                require(o['quote_expires'] and self.s.time()<o['quote_expires'],'报价已过期，请维护员重新报价',409,'QUOTE_EXPIRED')
                c.execute(update(orders).where(orders.c.id==id).values(state='PENDING',version=version+1,updated_at=self.s.time()))
                self.s.audit(c,a.name,'ACCEPT_CUSTOM_QUOTE',id)
                return self._order(c,id)
            return self.s.idempotent(c,a.name,'accept_quote',key,{'id':id,'version':version},action)

    def confirm(self,a:Actor,id,version,method,amount_cents,reference,reason,key):
        a.need('operator');require(method in ('TRIAL','MANUAL'),'开通方式不正确')
        integer(amount_cents,0,10000000,'核对金额（分）');reason=bounded_text(reason,1000,'核对原因',5)
        if method=='MANUAL':reference=bounded_text(reference,128,'外部收款核对凭据',5)
        else:require(amount_cents==0 and not reference,'试用开通不能记录收款金额或付款凭据')
        payload=dict(id=id,version=version,method=method,amount=amount_cents,reference=reference,reason=reason)
        with self.s.write() as c:
            def action():
                o=self._order(c,id);require(o['state']=='PENDING','订单不在可开通状态',409,'ORDER_STATE')
                require(o['version']==version,'申请已变化，请刷新',409,'STALE_VERSION')
                if method=='MANUAL':
                    require(amount_cents==o['amount_cents'],'人工核对金额与订单不一致',409,'AMOUNT_MISMATCH')
                    require(not row(c,select(orders.c.id).where(orders.c.settlement_ref==reference)),'核对凭据已用于另一申请',409,'REFERENCE_USED')
                previous=c.execute(select(func.max(grants.c.ends_at)).where(grants.c.owner==o['owner'],grants.c.revoked_at.is_(None))).scalar()
                start=max(self.s.time(),previous or self.s.time());end=stamp(add_months(parse(start),o['terms']['months']))
                g=dict(id=uid(),order_id=id,owner=o['owner'],terms=o['terms'],starts_at=start,ends_at=end,revoked_at=None,revoke_note=None,method=method)
                c.execute(insert(grants).values(**g))
                c.execute(update(orders).where(orders.c.id==id).values(state='FULFILLED_'+method,version=version+1,settlement_ref=reference if method=='MANUAL' else None,updated_at=self.s.time()))
                self.s.audit(c,a.name,'CONFIRM_'+method,id,{'amount_cents':amount_cents,'reason':reason,'starts_at':start,'ends_at':end})
                self.s.notice(c,o['owner'],'grant:'+g['id'],'服务权益已安排',f"{o['terms']['name']}，请在我的订阅查看起止日期。",'account')
                return g
            return self.s.idempotent(c,a.name,'confirm',key,payload,action)

    def cancel(self,a:Actor,id,version,key):
        with self.s.write() as c:
            def action():
                o=self._order(c,id);require(o['owner']==a.name or a.has('operator'),'服务申请不存在',404)
                require(o['version']==version and o['state'] in ('PENDING','REQUESTED','QUOTED'),'该申请不能取消；已开通服务需联系维护员',409)
                c.execute(update(orders).where(orders.c.id==id).values(state='CANCELLED',version=version+1,updated_at=self.s.time()))
                self.s.audit(c,a.name,'CANCEL_ORDER',id);return self._order(c,id)
            return self.s.idempotent(c,a.name,'cancel',key,{'id':id,'version':version},action)

    def list_grants(self,a:Actor,manage=False):
        if manage:a.need('operator')
        with self.s.read() as c:
            q=select(grants).order_by(grants.c.starts_at.desc()).limit(200)
            if not manage:q=q.where(grants.c.owner==a.name)
            found=rows(c,q)
        now=self.s.time()
        return [{**g,'status':'REVOKED' if g['revoked_at'] else ('SCHEDULED' if g['starts_at']>now else ('EXPIRED' if now>=g['ends_at'] else 'ACTIVE'))} for g in found]

    def revoke(self,a:Actor,id,reason,key):
        a.need('operator');reason=bounded_text(reason,1000,'撤销原因',5)
        with self.s.write() as c:
            def action():
                g=row(c,select(grants).where(grants.c.id==id));require(g,'权益不存在',404)
                require(not g['revoked_at'],'权益已经撤销',409)
                c.execute(update(grants).where(grants.c.id==id).values(revoked_at=self.s.time(),revoke_note=reason))
                self.s.audit(c,a.name,'REVOKE_GRANT',id,{'reason':reason,'refund_performed':False})
                self.s.notice(c,g['owner'],'revoke:'+id,'服务权益已撤销',reason+'；此记录不代表退款已完成。','account')
                return row(c,select(grants).where(grants.c.id==id))
            return self.s.idempotent(c,a.name,'revoke',key,{'id':id,'reason':reason},action)

    def _entitlements(self,c,owner):
        now=self.s.time()
        g=row(c,select(grants).where(grants.c.owner==owner,grants.c.revoked_at.is_(None),grants.c.starts_at<=now,grants.c.ends_at>now).order_by(grants.c.starts_at.desc()))
        if not g:return {'tier':'FREE','name':'免费使用','topic_limit':0,'site_limit':0,'scan_hours':24,'site_scan_hours':24,'capabilities':[],'ends_at':None,'grant_id':None}
        t=g['terms']
        return {k:t[k] for k in ('tier','name','topic_limit','site_limit','scan_hours','site_scan_hours')}|dict(capabilities=[x['capability'] for x in t['services']],ends_at=g['ends_at'],grant_id=g['id'])

    def entitlements(self,a:Actor):
        with self.s.read() as c:return self._entitlements(c,a.name)
