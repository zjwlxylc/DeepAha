"""Opt-in real PostgreSQL acceptance. No SQLite fallback or fake PASS.
Requires a dedicated DB named deepaha_experience_test_*. Each test owns a new schema.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from deepaha.product.service import Product
from deepaha.product.errors import Problem

@pytest.fixture
def pg(tmp_path):
    raw=os.getenv('DEEPAHA_EXPERIENCE_TEST_POSTGRES_URL')
    if not raw:pytest.skip('NOT_RUN: dedicated PostgreSQL URL not provided')
    url=make_url(raw)
    if not url.database or not url.database.startswith('deepaha_experience_test_'):
        pytest.fail('Refusing non-test database: dedicated deepaha_experience_test_* DB required')
    schema='experience_test_'+uuid.uuid4().hex
    admin=create_engine(url)
    with admin.begin() as c:c.execute(text('CREATE SCHEMA '+schema))
    scoped=url.update_query_dict({'options':'-csearch_path='+schema})
    product=Product(scoped.render_as_string(hide_password=False),tmp_path/'objects')
    try:
        product.initialize();product.create_account('pgowner','test-only-123',['operator'])
        yield product
    finally:
        product.db.engine.dispose()
        with admin.begin() as c:c.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()


def test_real_pg_two_clients_profile_compare_and_set(pg):
    other=Product(pg.database_url,pg.object_root)
    try:
        v=pg.profile_state(actor='pgowner')['version']
        def update(p):
            try:p.patch_profile({'major':'广告学'},v,actor='pgowner');return 'OK'
            except Problem as e:return e.code
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(update,[pg,other]))
        assert result.count('OK')==1 and result.count('PROFILE_CHANGED')==1
    finally:other.db.engine.dispose()


def test_real_pg_atomic_task_claim_no_remote_calls(pg):
    from deepaha.product.dispatch_policy import claim
    source=pg.add_source('受控测试源','https://test.example.org',actor='pgowner')
    pg.create_task(source['id'],'https://test.example.org/notice',actor='pgowner',request_key='pg-claim')
    other=Product(pg.database_url,pg.object_root)
    try:
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(lambda pair:claim(pair[0],'default',None,pair[1]),[(pg,'one'),(other,'two')]))
        assert sum(r is not None for r in result)==1
    finally:other.db.engine.dispose()
