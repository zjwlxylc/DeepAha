"""Backup-first extension upgrade; never replace existing accounts or official records."""
from sqlalchemy import inspect, select
import pytest
from .test_contract import svc
from deepaha.product.models import Base,Account,Profile,Meta,EXPERIENCE_TABLE_NAMES
from deepaha.product.errors import Problem


def test_additive_upgrade_backup_and_idempotency(svc,tmp_path):
    from deepaha.product import upgrade
    assert hasattr(upgrade,'upgrade_experience'), 'explicit extension migration must exist'
    svc.set_profile({'major':'广告学','cities':['宁波']},actor='reader')
    with svc.db.tx(False) as s:
        before=[(a.id,a.username,a.password_hash,list(a.roles)) for a in s.scalars(select(Account).order_by(Account.id))]
        profiles=[(p.account_id,p.data) for p in s.scalars(select(Profile))]
    tables=[t for t in Base.metadata.sorted_tables if t.name in EXPERIENCE_TABLE_NAMES]
    Base.metadata.drop_all(svc.db.engine,tables=list(reversed(tables)))
    with svc.db.tx() as s:
        r=s.get(Meta,'experience_schema_version')
        if r:s.delete(r)
    backup=tmp_path/'before-extension.zip'
    result=upgrade.upgrade_experience(svc,backup)
    assert result['backup_verified'] and backup.exists()
    assert EXPERIENCE_TABLE_NAMES.issubset(inspect(svc.db.engine).get_table_names())
    assert svc.profile_state(actor='reader')['profile']=={'major':'广告学','cities':['宁波']}
    with svc.db.tx(False) as s:
        assert before==[(a.id,a.username,a.password_hash,list(a.roles)) for a in s.scalars(select(Account).order_by(Account.id))]
        assert profiles==[(p.account_id,p.data) for p in s.scalars(select(Profile))]
    second=upgrade.upgrade_experience(svc,tmp_path/'unused.zip')
    assert second['already_current'] and not (tmp_path/'unused.zip').exists()


def test_initializer_refuses_silent_upgrade(svc):
    tables=[t for t in Base.metadata.sorted_tables if t.name in EXPERIENCE_TABLE_NAMES]
    Base.metadata.drop_all(svc.db.engine,tables=list(reversed(tables)))
    with pytest.raises(Problem) as err:svc.initialize()
    assert err.value.code=='EXPERIENCE_UPGRADE_REQUIRED'


def test_release_generation_blocks_automatic_rollback_to_old_workers():
    import json
    from pathlib import Path
    data=json.loads(Path('RELEASE_COMPATIBILITY.json').read_text(encoding='utf-8'))
    assert data['database_generation'].endswith('-experience1')
    assert not data['code_rollback_compatible_with']
    assert data['schema_change_in_release'] is True


def test_postgres_backup_manifest_precedes_additive_ddl(svc,tmp_path,monkeypatch):
    """Exercise PG backup branch with real backup bytes/DDL, isolated SQLite rows."""
    import hashlib,json,subprocess
    from types import SimpleNamespace
    from deepaha.product import upgrade
    tables=[t for t in Base.metadata.sorted_tables if t.name in EXPERIENCE_TABLE_NAMES]
    Base.metadata.drop_all(svc.db.engine,tables=list(reversed(tables)))
    with svc.db.tx() as s:
        row=s.get(Meta,'experience_schema_version')
        if row:s.delete(row)
    original_inspect=inspect
    monkeypatch.setattr(upgrade,'inspect',lambda engine:original_inspect(svc.db.engine))
    import shutil
    monkeypatch.setattr(shutil,'which',lambda name:'/usr/bin/'+name)
    def command(args,**kw):
        if args[0]=='pg_dump':kw['stdout'].write(b'controlled dump bytes')
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(subprocess,'run',command)
    product=SimpleNamespace(database_url='postgresql://test_user@localhost/test_db',object_root=svc.object_root,
        db=SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),tx=svc.db.tx))
    backup=tmp_path/'postgres-backup'
    result=upgrade.upgrade_experience(product,backup)
    assert result['backup_verified']
    hashes=json.loads((backup/'SHA256SUMS.json').read_text())
    assert set(hashes)=={'database.dump','objects.tar.gz'}
    assert all(hashlib.sha256((backup/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
    assert EXPERIENCE_TABLE_NAMES.issubset(original_inspect(svc.db.engine).get_table_names())
