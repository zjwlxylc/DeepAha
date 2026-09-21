"""Small user-facing queries and idempotent save; no new tables or qualification rules."""
from sqlalchemy import select, func
from .models import Account, TargetAction, Action, TargetNotice, Notice, now


def summary(product, actor):
    """Count the entire user's workspace, never a paginated list or another tenant."""
    with product.db.tx(False) as s:
        a=product._account(s,actor)
        counts={k:0 for k in ('SAVED','PREPARING','APPLIED','WAITING','COMPLETED','DISMISSED')}
        for model in (TargetAction,Action):
            for status,count in s.execute(select(model.status,func.count()).where(model.account_id==a.id).group_by(model.status)):
                counts[status]=counts.get(status,0)+count
        unread=0
        for model in (TargetNotice,Notice):
            unread+=s.scalar(select(func.count()).select_from(model).where(model.account_id==a.id,model.state=='UNREAD',model.due_at<=now())) or 0
        from .membership import unread_count
        unread+=unread_count(s.connection(),actor)
        return {'counts':counts,'action_total':sum(counts.values()),'unread_count':unread}


def mount_mobile(app,product,user):
    from fastapi import Request
    @app.get('/api/me/summary')
    def me_summary(req:Request):return summary(product,user(req))
    @app.get('/api/me/actions/{id}')
    def action(id:str,req:Request):return product.action_state(id,actor=user(req))
    @app.post('/api/me/actions/{id}/save')
    def save(id:str,req:Request):return product.save_opportunity(id,actor=user(req,write=True))
