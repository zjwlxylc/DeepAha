from sqlalchemy import create_engine,select,inspect
from .test_api import client,login
from .test_contract import svc
from .test_services_r3 import trial,P
from deepaha_membership.db import orders,Store
from deepaha.product.backup import create_backup
from deepaha.product.deployment import migrate_sqlite_backup


def test_full_migration_keeps_subscription_and_pauses_runtime(client,svc,tmp_path):
    trial(client)
    login(client,'operator');cfg=client.get(P+'/manage/runtime').json()
    assert client.put(P+'/manage/runtime',json={'version':cfg['version'],'enabled':True,'allow_site_enqueue':True,'max_jobs':2,'connection':'default'}).status_code==200
    backup=tmp_path/'full.zip';create_backup(svc.database_url,svc.object_root,backup)
    target='sqlite:///'+str(tmp_path/'target.db')
    report=migrate_sqlite_backup(backup,target,tmp_path/'target-objects',require_postgres=False)
    engine=create_engine(target)
    try:
        assert 'mbr_orders' in report['database']['tables']
        Store(engine).assert_ready()
        with engine.connect() as c:assert len(list(c.execute(select(orders))))==1
        from deepaha.product.service import Product
        from deepaha.product.membership import runtime_config
        p=Product(target,tmp_path/'target-objects')
        settings=runtime_config(p);assert settings['enabled'] is False and settings['allow_site_enqueue'] is False
        p.db.engine.dispose()
    finally:engine.dispose()
