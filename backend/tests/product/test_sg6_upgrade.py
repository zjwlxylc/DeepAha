from pathlib import Path
from sqlalchemy import inspect, text
from .test_contract import svc,packet


def test_sg6_upgrade_backfills_current_actions_and_feedback_backup_first(tmp_path):
    from deepaha.product.service import Product
    from deepaha.product.models import TargetActionEvent,FeedbackCandidate
    from deepaha.product.upgrade import upgrade_action_loop,ACTION_LOOP_TABLE_NAMES
    # Build a current database, create user state, then simulate an SG5.1 schema by dropping only SG6 tables/meta.
    p=Product(f'sqlite:///{tmp_path}/old.db',tmp_path/'objects');p.initialize()
    p.create_account('reviewer','long-password-123',['reviewer']);p.create_account('operator','long-password-123',['operator']);p.create_account('reader','long-password-123',['user'])
    src=p.add_source('源','https://research.example.org/',actor='operator');a=p.ingest(src['id'],packet(),actor='operator');r=p.decide(a['id'],'APPROVE',a['preview_hash'],'','u1',actor='reviewer');target=r['catalog_target_ids'][0]
    p.set_action(target,'SAVED',actor='reader');p.feedback(target,{'useful':True,'outcome':'APPLIED'},actor='reader')
    # The fixture above already wrote SG6 rows; emulate old schema by dropping SG6 tables and meta while preserving old state tables.
    with p.db.engine.begin() as c:
        c.exec_driver_sql('DROP TABLE product_feedback_candidates');c.exec_driver_sql('DROP TABLE product_target_action_events');c.exec_driver_sql("DELETE FROM product_meta WHERE key='action_loop_schema_version'")
    old=Product(p.database_url,p.object_root)
    backup=tmp_path/'before-sg6.zip'
    result=upgrade_action_loop(old,backup)
    assert result['backup_verified'] and backup.exists()
    assert ACTION_LOOP_TABLE_NAMES.issubset(set(inspect(old.db.engine).get_table_names()))
    with old.db.tx(False) as s:
        assert s.execute(text('select count(*) from product_target_action_events')).scalar_one()==1
        assert s.execute(text('select count(*) from product_feedback_candidates')).scalar_one()==1
    again=upgrade_action_loop(old,tmp_path/'unused.zip')
    assert again['already_current'] and again['data_modified'] is False
