"""The Windows launcher upgrades existing local accounts before serving."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
from deepaha.product.models import ACCESS_TABLE_NAMES
from deepaha.product.service import Product


def test_launcher_backs_up_and_upgrades_access_without_changing_password(tmp_path):
    root=Path(__file__).resolve().parents[3]
    spec=importlib.util.spec_from_file_location('local_launcher',root/'scripts/launch_product.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    database=tmp_path/'deepaha.db'
    p=Product('sqlite:///'+database.as_posix(),tmp_path/'objects');p.initialize()
    p.create_account('local_owner','1234',['operator']);p.db.engine.dispose()
    with sqlite3.connect(database) as c:
        c.execute('DROP TABLE product_invitation_redemptions')
        c.execute('DROP TABLE product_password_resets')
        c.execute('DROP TABLE product_invitations')
        before=c.execute('SELECT username,password_hash,roles FROM product_accounts').fetchall()
    env={**os.environ,'PYTHONPATH':str(root/'backend/src'),'DEEPAHA_DATA_DIR':str(tmp_path),'DEEPAHA_DATABASE_URL':'sqlite:///'+database.as_posix(),'PYTHONUTF8':'1'}
    backup=launcher.upgrade_local_access(database,[sys.executable,'-m','deepaha.product.cli'],env)
    assert backup.exists()
    with sqlite3.connect(backup) as c:
        assert c.execute('SELECT username,password_hash,roles FROM product_accounts').fetchall()==before
        assert 'product_invitations' not in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    with sqlite3.connect(database) as c:
        assert ACCESS_TABLE_NAMES.issubset({r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        assert c.execute('SELECT username,password_hash,roles FROM product_accounts').fetchall()==before
    assert launcher.upgrade_local_access(database,[sys.executable,'-m','deepaha.product.cli'],env) is None
