from pathlib import Path
from sqlalchemy import inspect, text
import pytest
from .test_contract import svc


def remove_membership(svc):
    from deepaha_membership.db import metadata
    metadata.drop_all(svc.db.engine)


def test_old_r2_needs_explicit_backup_upgrade(svc,tmp_path):
    from deepaha.product.services_upgrade import upgrade_services
    from deepaha.product.errors import Problem
    remove_membership(svc)
    with pytest.raises(Problem):svc.initialize()
    before=svc.get_profile(actor='reader')
    b=tmp_path/'before.zip'
    result=upgrade_services(svc,b)
    assert b.is_file() and result['backup_verified']
    assert svc.get_profile(actor='reader')==before
    assert upgrade_services(svc,tmp_path/'unused.zip')['already_current']
    assert not (tmp_path/'unused.zip').exists()
    from deepaha.product.backup import restore_backup
    restore_backup(b,tmp_path/'restored')
    import sqlite3
    with sqlite3.connect(tmp_path/'restored'/'deepaha.db') as c:
        assert not c.execute("SELECT name FROM sqlite_master WHERE name='mbr_meta'").fetchone()


def test_partial_schema_fails_without_fabricating_repair(svc,tmp_path):
    from deepaha.product.services_upgrade import upgrade_services
    from deepaha.product.errors import Problem
    with svc.db.engine.begin() as c:c.execute(text('DROP TABLE mbr_notices'))
    with pytest.raises(Problem):upgrade_services(svc,tmp_path/'bad.zip')
    assert 'mbr_notices' not in inspect(svc.db.engine).get_table_names()


def test_unknown_schema_fails_closed(svc,tmp_path):
    from deepaha.product.services_upgrade import upgrade_services
    from deepaha.product.errors import Problem
    with svc.db.engine.begin() as c:c.execute(text("UPDATE mbr_meta SET value='99' WHERE key='schema_version'"))
    with pytest.raises(Problem):upgrade_services(svc,tmp_path/'bad.zip')
