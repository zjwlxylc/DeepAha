from pathlib import Path
import json
import os
import subprocess
import shutil
import sys

import pytest

from deepaha.product.backup import create_backup
from deepaha.product.config import Settings
from deepaha.product.deployment import deployment_check, migrate_sqlite_backup
from deepaha.product.errors import Problem
from deepaha.product.service import Product

ROOT=Path(__file__).resolve().parents[3]


def test_sqlite_backup_migration_preserves_database_objects_and_revokes_sessions(tmp_path):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source_url='sqlite:///'+str(source_dir/'deepaha.db')
    source=Product(source_url,source_dir/'objects');source.initialize()
    source.create_account('owner','StrongPassword-123',['user','reviewer','operator'])
    source.login('owner','StrongPassword-123','127.0.0.1')
    object_manifest=source.store.save({'probe.txt':b'sg8-a-portable-object'})
    backup=tmp_path/'portable.zip'
    create_backup(source_url,source_dir/'objects',backup)
    source.db.engine.dispose()

    target_dir=tmp_path/'target';target_dir.mkdir()
    target_url='sqlite:///'+str(target_dir/'deepaha.db')
    report=migrate_sqlite_backup(backup,target_url,target_dir/'objects',require_postgres=False)
    assert report['migrated'] is True
    assert report['credentials_migrated'] is False
    assert report['sessions_revoked'] is True
    assert report['database']['tables']['product_accounts']==1
    assert report['objects']['files']>=2  # bytes + metadata

    target=Product(target_url,target_dir/'objects')
    # Account/hash data survives, but the restored browser session does not.
    assert target.login('owner','StrongPassword-123','127.0.0.1')['username']=='owner'
    assert target.store.one(object_manifest,'probe.txt')==b'sg8-a-portable-object'
    target.db.engine.dispose()


def test_migration_refuses_nonempty_destination(tmp_path):
    src=tmp_path/'src';src.mkdir();src_url='sqlite:///'+str(src/'deepaha.db')
    product=Product(src_url,src/'objects');product.initialize();product.create_account('owner','StrongPassword-123',['user'])
    backup=tmp_path/'b.zip';create_backup(src_url,src/'objects',backup);product.db.engine.dispose()
    dst=tmp_path/'dst';dst.mkdir();dst_url='sqlite:///'+str(dst/'deepaha.db')
    first=migrate_sqlite_backup(backup,dst_url,dst/'objects',require_postgres=False)
    assert first['migrated']
    with pytest.raises(Problem) as error:
        migrate_sqlite_backup(backup,dst_url,dst/'objects',require_postgres=False)
    assert error.value.code in {'MIGRATION_OBJECTS_NONEMPTY','MIGRATION_NONEMPTY'}


def test_production_settings_are_fail_closed(monkeypatch,tmp_path):
    monkeypatch.setenv('DEEPAHA_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setenv('DEEPAHA_MODE','production')
    monkeypatch.setenv('DEEPAHA_DATABASE_URL','sqlite:///'+str(tmp_path/'bad.db'))
    monkeypatch.setenv('DEEPAHA_SECURE_COOKIE','1')
    monkeypatch.setenv('DEEPAHA_ALLOWED_HOSTS','deepaha.com')
    monkeypatch.setenv('DEEPAHA_ALLOWED_ORIGINS','https://deepaha.com')
    with pytest.raises(RuntimeError,match='PostgreSQL'):
        Settings.from_env()
    monkeypatch.setenv('DEEPAHA_DATABASE_URL','postgresql+psycopg://user:pw@localhost/db')
    monkeypatch.setenv('DEEPAHA_ALLOWED_HOSTS','*')
    with pytest.raises(RuntimeError,match='secure cookies'):
        Settings.from_env()


def test_deploy_check_never_claims_local_sqlite_is_production(tmp_path):
    data=tmp_path/'data';settings=Settings(data_dir=data,database_url='sqlite:///'+str(data/'deepaha.db'),mode='local')
    p=Product(settings.database_url,data/'objects');p.initialize();p.create_account('owner','StrongPassword-123',['user']);p.db.engine.dispose()
    result=deployment_check(settings)
    assert result['status']=='FAIL'
    assert {'mode_production','secure_cookie','postgresql_url','database_dialect'}.intersection(result['failed_required'])
    assert result['wma_called'] is False
    assert result['data_modified'] is False


def test_sg8a_server_assets_are_safe_and_versioned(tmp_path):
    required=[
        ROOT/'infra/sg8a/production.env.example',ROOT/'infra/sg8a/staging.env.example',
        ROOT/'infra/sg8a/systemd/deepaha-api@.service',ROOT/'infra/sg8a/systemd/deepaha-worker@.service',
        ROOT/'infra/sg8a/nginx/deepaha-production.conf.example',ROOT/'infra/sg8a/nginx/deepaha-staging.conf.example',
        ROOT/'ops/sg8a/bootstrap-host.sh',ROOT/'ops/sg8a/install-release.sh',ROOT/'ops/sg8a/rollback.sh',
        ROOT/'ops/sg8a/backup-postgres.sh',ROOT/'ops/sg8a/verify-backup.sh',ROOT/'ops/sg8a/restore-postgres-backup.sh',ROOT/'ops/sg8a/smoke.sh',ROOT/'ops/sg8a/preflight-host.sh',
        ROOT/'RELEASE_COMPATIBILITY.json',
    ]
    assert all(path.exists() for path in required)
    for script in (ROOT/'ops/sg8a').glob('*.sh'):
        # Resolve PATH explicitly: Windows CreateProcess otherwise prefers System32's
        # WSL launcher even when a working Git Bash is first on PATH.
        bash=shutil.which('bash')
        assert bash, 'A working Bash is required for deployment script validation'
        subprocess.run([bash,'-n',str(script)],check=True)
    compatibility=json.loads((ROOT/'RELEASE_COMPATIBILITY.json').read_text(encoding='utf-8'))
    assert compatibility['release']=='3.8.0-rc1'
    assert compatibility['schema_change_in_release'] is False
    api_unit=(ROOT/'infra/sg8a/systemd/deepaha-api@.service').read_text(encoding='utf-8')
    assert 'EnvironmentFile=/etc/deepaha/%i.env' in api_unit
    assert 'ReadWritePaths=/var/lib/deepaha/%i' in api_unit
    prod=(ROOT/'infra/sg8a/nginx/deepaha-production.conf.example').read_text(encoding='utf-8')
    stage=(ROOT/'infra/sg8a/nginx/deepaha-staging.conf.example').read_text(encoding='utf-8')
    assert 'limit_req zone=deepaha_auth' in prod
    assert 'Strict-Transport-Security' in prod
    assert 'auth_basic_user_file' in stage
    import yaml
    compose=yaml.safe_load((ROOT/'infra/sg8a/compose.dev.yaml').read_text(encoding='utf-8'))
    assert {'postgres','api'} <= set(compose['services'])
    assert compose['services']['api']['ports']==['127.0.0.1:18000:8000']
    combined='\n'.join(path.read_text(encoding='utf-8',errors='ignore') for path in required if path.suffix not in {'.json'})
    assert 'DEEPAHA_WMA_API_KEY=' in (ROOT/'infra/sg8a/production.env.example').read_text(encoding='utf-8')
    assert 'DEEPAHA_WMA_AGENT_ID=' in (ROOT/'infra/sg8a/production.env.example').read_text(encoding='utf-8')


def test_envtool_does_not_expand_shell_values(tmp_path):
    env=tmp_path/'test.env'
    env.write_text('SAFE=value\nPASSWORD=a$HOME#literal\n',encoding='utf-8')
    tool=ROOT/'ops/sg8a/envtool.py'
    result=subprocess.run([sys.executable,str(tool),'get',str(env),'PASSWORD'],capture_output=True,text=True,check=True)
    assert result.stdout.strip()=='a$HOME#literal'
