"""Adapter checked against the readable main Product interface, NOT R2 integration-tested."""
from urllib.parse import urlsplit
from .errors import require

class ProductPort:
    def __init__(self,product,settings,connections=None):
        self.p,self.settings,self.connections=product,settings,connections

    def register(self,a,lead):
        a.need('operator')
        return self.p.add_source(lead['name'],lead['approved_url'],actor=a.name,
            brief=lead['public_brief'],allowed_hosts=[urlsplit(lead['approved_url']).hostname],tier=lead['tier'])

    def enable(self,a,lead):
        a.need('operator')
        # Reuse the source API rather than writing core tables. Existing disabled
        # sources stay disabled until this explicit operator action.
        current=self.register(a,lead)
        require(current['id']==lead['source_id'],'来源关联发生变化，请重新核对',409)
        return self.p.source_status(current['id'],True,'维护员明确授权已审核的用户来源',actor=a.name,expected_version=current['policy_version'])

    def enqueue(self,a,lead,key,connection):
        a.need('operator')
        if self.connections is not None:definitions=self.connections()
        else:
            from deepaha.product.config import BindingRegistry
            definitions=BindingRegistry(self.settings.data_dir,self.settings.mode).definitions()
        require(connection in definitions,'宿主未登记该执行连接',404,'UNKNOWN_CONNECTION')
        return self.p.create_task(lead['source_id'],lead['approved_url'],actor=a.name,request_key=key,
            instruction=('调查范围由维护员核验：'+lead['public_brief']+'。仅处理公开机会资料，保留官方原文和附件依据；结果仍须整体审核，不直接发布。'),
            kind='INVESTIGATE',budget_seconds=1200,connection_ref=connection)

    def catalog(self,**kwargs):return self.p.catalog(**kwargs)
    def task(self,a,id):
        a.need('operator');return self.p.task_detail(id,actor=a.name)

    def catalog_for_source(self,lead,*,offset=0,limit=50,read_version=None,**filters):
        """Read only the existing public projection with exact source lineage.

        A host/path substring is deliberately not used as source identity. The
        current Product models/SQL contract still requires exact-R2 integration
        validation, called out in the release report.
        """
        from sqlalchemy import select,func
        from deepaha.product.models import Identity,Opportunity,CatalogTarget,Meta
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=50,'分页参数不正确')
        with self.p.db.tx(False) as s:
            version=int(s.get(Meta,'catalog_revision').value)
            require(read_version is None or version==read_version,'目录版本已更新',409,'CATALOG_CHANGED')
            identities=select(Identity.opportunity_id).where(Identity.source_id==lead['source_id'])
            stmt=(select(CatalogTarget,Opportunity).join(Opportunity,CatalogTarget.opportunity_id==Opportunity.opportunity_id)
                  .where(CatalogTarget.opportunity_id.in_(identities),CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
                  .order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc()))
            total=s.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
            items=[self.p._target(t,o) for t,o in s.execute(stmt.offset(offset).limit(limit))]
            # expire the identity map before rechecking the catalog counter.
            s.expire_all()
            require(int(s.get(Meta,'catalog_revision').value)==version,'目录版本已更新',409,'CATALOG_CHANGED')
            return dict(items=items,total=total,read_version=version,has_more=offset+limit<total)
