"""No production data or credentials are touched by these isolated tests."""
from pathlib import Path
import json,zipfile
import pytest
from .test_contract import svc,packet
from deepaha.product.errors import Problem


def test_backup_restore_into_empty_directory(svc,tmp_path):
    from deepaha.product.backup import create_backup,restore_backup,verify_backup
    r=svc.ingest(svc.test_source,packet(),actor='operator')
    svc.decide(r['id'],'APPROVE',r['preview_hash'],'','backup-proof',actor='reviewer')
    token=svc.login('reader','long-password-123')['token']
    destination=tmp_path/'copy.zip'
    create_backup(svc.database_url,svc.object_root,destination)
    assert verify_backup(destination)['backup_valid']
    restored=tmp_path/'restored';restore_backup(destination,restored)
    from deepaha.product.service import Product
    p=Product('sqlite:///'+str(restored/'deepaha.db'),restored/'objects')
    assert p.catalog()['total']==1
    assert p.raw_file(r['id'],'report.md',actor='reviewer')
    with pytest.raises(Problem):p.authenticate(token)
    with pytest.raises(Problem):restore_backup(destination,restored)
    with zipfile.ZipFile(destination) as z:
        assert not any(x.endswith(('.enc','.credential-key')) for x in z.namelist())


def test_backup_rejects_traversal(tmp_path):
    from deepaha.product.backup import verify_backup
    import hashlib
    zpath=tmp_path/'bad.zip'
    with zipfile.ZipFile(zpath,'w') as z:
        z.writestr('../evil',b'x')
        z.writestr('BACKUP_MANIFEST.json',json.dumps({'schema_version':1,'files':{'../evil':hashlib.sha256(b'x').hexdigest()}}))
    with pytest.raises(Problem):verify_backup(zpath)


def test_local_credentials_encrypted_and_not_returned(tmp_path):
    from deepaha.product.config import ConnectionConfig
    c=ConnectionConfig(tmp_path)
    c.save('agent_valid','deepaha','a-private-test-secret',False)
    assert c.load()['api_key']=='a-private-test-secret'
    assert 'a-private-test-secret' not in json.dumps(c.public())
    assert b'a-private-test-secret' not in (tmp_path/'wma-connection.enc').read_bytes()
    c.save('agent_valid','deepaha','',True)
    assert c.public()['enabled']
    with pytest.raises(Problem):ConnectionConfig(tmp_path,'production').save('a','b','test-secret',True)


def test_schema_init_is_idempotent(svc):
    r=svc.ingest(svc.test_source,packet(),actor='operator')
    svc.initialize();svc.initialize()
    assert svc.preview(r['id'],actor='reviewer')['id']==r['id']


def test_successful_worker_keeps_remote_result_pending(svc):
    import asyncio
    from deepaha.product.worker import run_once
    from deepaha.product.storage import unpack
    from deepaha.investigations.wma import WmaSessionRef
    class FakeRemote:
        calls=[]
        async def create(self,id,checkpoint):
            self.calls.append('create');checkpoint('runtime','session');return WmaSessionRef('runtime','session')
        def binding_evidence(self):return {'source':'CONTRACT_TEST'}
        async def upload(self,path,content):self.calls.append('upload')
        async def prompt(self,text,timeout_seconds):self.calls.append('prompt');return 'end_turn'
        async def download(self,path,max_bytes):return unpack(packet())[path.split('/result/')[1]]
        async def aclose(self):pass
    task=svc.create_task(svc.test_source,'https://research.example.org/notices/101',actor='operator',request_key='fresh-worker')
    result=asyncio.run(run_once(svc,lambda:FakeRemote()))
    t=svc.task_detail(task['id'],actor='operator')
    assert t['status']=='READY',result
    assert FakeRemote.calls.count('prompt')==1
    assert svc.preview(t['revision_id'],actor='reviewer')['status']=='PENDING'
    assert svc.catalog()['total']==0


def test_source_schedule_remembers_authorized_operator(svc):
    from datetime import timedelta
    from deepaha.product.models import SourceProfile,now
    from deepaha.product.worker import schedule_due
    svc.schedule_source(svc.test_source,6,actor='operator')
    with svc.db.tx() as s:s.get(SourceProfile,svc.test_source).next_due=now()-timedelta(seconds=5)
    assert schedule_due(svc)==1
    assert schedule_due(svc)==0
    assert len(svc.tasks(actor='operator'))==1
    with svc.db.tx() as s:s.get(SourceProfile,svc.test_source).next_due=now()-timedelta(seconds=5)
    svc.revoke_account('operator')
    assert schedule_due(svc)==0


def test_unrecognized_source_asset_is_not_reported_as_imported(svc):
    with pytest.raises(Problem):svc.import_sources({'not_sources':[{'name':'unexpected'}]},actor='operator')
    assert svc.import_sources({'sources':[]},actor='operator')['status']=='NO_CHANGES'


def test_sg1_upgrade_is_backup_first_and_backfills_existing_publication(tmp_path):
    """An rc2 database upgrades additively without re-reviewing its approved packet."""
    import sqlite3
    from sqlalchemy import select, func
    from deepaha.product.service import Product
    from deepaha.product.errors import Problem
    from deepaha.product.upgrade import upgrade_actionable_catalog
    from deepaha.product.backup import verify_backup
    from deepaha.product.models import Opportunity, Publication, Decision, CatalogTarget

    data=tmp_path/'legacy';data.mkdir()
    db=data/'deepaha.db';objects=data/'objects'
    legacy=Product('sqlite:///'+str(db),objects);legacy.initialize()
    legacy.create_account('reviewer','long-password-123',['reviewer'])
    legacy.create_account('operator','long-password-123',['operator'])
    source=legacy.add_source('海湾研究中心','https://research.example.org/',actor='operator')
    revision=legacy.ingest(source['id'],packet(),actor='operator')
    receipt=legacy.decide(revision['id'],'APPROVE',revision['preview_hash'],'','pre-sg1',actor='reviewer')
    with legacy.db.tx(False) as s:
        before=(
            s.scalar(select(func.count()).select_from(Opportunity)),
            s.scalar(select(func.count()).select_from(Publication)),
            s.scalar(select(func.count()).select_from(Decision)),
        )
    legacy.db.engine.dispose()

    # Turn the fixture into an rc2-shaped store: keep all authoritative rows,
    # remove only SG1 projection tables/meta that did not exist yet.
    con=sqlite3.connect(db)
    con.execute('PRAGMA foreign_keys=OFF')
    for table in ['product_target_notices','product_target_feedback','product_target_actions',
                  'product_catalog_targets','product_opportunity_units']:
        con.execute(f'DROP TABLE {table}')
    con.execute("DELETE FROM product_meta WHERE key='actionable_schema_version'")
    con.commit();con.close()

    old=Product('sqlite:///'+str(db),objects)
    with pytest.raises(Problem) as exc:
        old.initialize()
    assert exc.value.code=='ACTIONABLE_UPGRADE_REQUIRED'

    backup=tmp_path/'before-sg1.zip'
    result=upgrade_actionable_catalog(old,backup)
    assert result['backup_verified'] and result['catalog_targets_created']==1
    assert verify_backup(backup)['backup_valid']
    assert old.catalog()['total']==1
    card=old.catalog()['items'][0]
    assert card['id'].startswith('unit_') and card['root_public_id']==receipt['public_ids'][0]
    with old.db.tx(False) as s:
        after=(
            s.scalar(select(func.count()).select_from(Opportunity)),
            s.scalar(select(func.count()).select_from(Publication)),
            s.scalar(select(func.count()).select_from(Decision)),
        )
        assert s.scalar(select(func.count()).select_from(CatalogTarget))==1
    assert after==before

    again=upgrade_actionable_catalog(old,tmp_path/'unused-second-backup.zip')
    assert again['already_current'] and again['catalog_targets']==1
    assert not (tmp_path/'unused-second-backup.zip').exists()


def test_sg1_upgrade_backfills_when_tables_exist_but_projection_is_missing(tmp_path):
    """A prior generic create_all must not make an unbackfilled rc2 DB look SG1-complete."""
    from sqlalchemy import delete
    from deepaha.product.service import Product
    from deepaha.product.upgrade import upgrade_actionable_catalog
    from deepaha.product.models import CatalogTarget,OpportunityUnit
    data=tmp_path/'half-upgraded';data.mkdir();db=data/'deepaha.db';objects=data/'objects'
    p=Product('sqlite:///'+str(db),objects);p.initialize()
    p.create_account('reviewer','long-password-123',['reviewer']);p.create_account('operator','long-password-123',['operator'])
    source=p.add_source('海湾研究中心','https://research.example.org/',actor='operator')
    revision=p.ingest(source['id'],packet(),actor='operator');p.decide(revision['id'],'APPROVE',revision['preview_hash'],'','half-upgraded',actor='reviewer')
    with p.db.tx() as s:
        s.execute(delete(CatalogTarget));s.execute(delete(OpportunityUnit))
    result=upgrade_actionable_catalog(p,tmp_path/'half-before-sg1.zip')
    assert not result.get('already_current',False)
    assert result['catalog_targets_created']==1
    assert p.catalog()['total']==1
