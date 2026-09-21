"""Atomic custom-service request plus nominated public website, with one retry key."""
from .commerce import bounded_text
from .urls import canonicalize
from .errors import require


def create_custom_request(store,commerce,contributions,a,code,version,key,note,site_name,site_url,consent):
    url=canonicalize(site_url);name=bounded_text(site_name,200,'网站名称')
    note=bounded_text(note,2000,'定制需求',5)
    require(consent is True,'请同意将公开网址提交到来源审核')
    payload=dict(code=code,version=version,note=note,site_name=name,site_url=url,consent=consent)
    with store.write() as connection:
        def action():
            require(commerce._plan(connection,code)['terms']['tier']=='CUSTOM','此入口用于定制服务申请')
            order=commerce._create_order_row(connection,a,code,version,note)
            submission=contributions._submit_row(connection,a,name,url,'CUSTOM',note)
            return {'order':order,'submission':submission}
        return store.idempotent(connection,a.name,'custom_request',key,payload,action)
