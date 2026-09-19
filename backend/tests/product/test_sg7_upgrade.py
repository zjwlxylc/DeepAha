import hashlib
from pathlib import Path
from sqlalchemy import inspect, select, text

from .test_contract import svc, packet


def _authority_counts(svc):
    from deepaha.product.models import Decision, Opportunity, Publication, Revision, Snapshot
    from sqlalchemy import func
    with svc.db.tx(False) as s:
        return {cls.__tablename__:s.scalar(select(func.count()).select_from(cls)) or 0 for cls in [Snapshot,Revision,Decision,Publication,Opportunity]}


def test_sg7_upgrade_is_backup_first_additive_idempotent_and_preserves_authority_and_objects(svc,tmp_path):
    from deepaha.product.models import LAB_TABLE_NAMES, Meta
    from deepaha.product.upgrade import upgrade_opportunity_lab
    # Create one real-looking persisted source result before simulating the SG6.2 schema.
    r=svc.ingest(svc.test_source,packet('升级保留样本'),actor='operator')
    svc.decide(r['id'],'APPROVE',r['preview_hash'],'','sg7-upgrade-approve',actor='reviewer')
    marker=svc.object_root/'sg7-preserve-marker.bin';marker.parent.mkdir(parents=True,exist_ok=True);marker.write_bytes(b'preserve-me')
    digest=hashlib.sha256(marker.read_bytes()).hexdigest();before=_authority_counts(svc)

    # Simulate a user-approved SG6.2 database: all production data remains, only SG7 tables/meta are absent.
    with svc.db.engine.begin() as conn:
        for name in ['product_lab_run_results','product_lab_pair_truths','product_lab_exposures','product_lab_runs','product_lab_gold_cases','product_lab_twins','product_lab_enrollments']:
            conn.execute(text(f'DROP TABLE IF EXISTS {name}'))
        conn.execute(text("DELETE FROM product_meta WHERE key='opportunity_lab_schema_version'"))
    assert not LAB_TABLE_NAMES.issubset(set(inspect(svc.db.engine).get_table_names()))

    backup=tmp_path/'before-sg7.zip'
    first=upgrade_opportunity_lab(svc,backup)
    assert first['backup_verified'] is True and backup.exists()
    assert first['production_facts_modified'] is False and first['wma_called'] is False
    assert LAB_TABLE_NAMES.issubset(set(inspect(svc.db.engine).get_table_names()))
    assert _authority_counts(svc)==before
    assert hashlib.sha256(marker.read_bytes()).hexdigest()==digest
    with svc.db.tx(False) as s:assert s.get(Meta,'opportunity_lab_schema_version').value=='2'

    unused=tmp_path/'unused.zip';second=upgrade_opportunity_lab(svc,unused)
    assert second['already_current'] is True and second['data_modified'] is False
    assert not unused.exists()
    assert _authority_counts(svc)==before


def test_windows_launcher_runs_sg7_after_sg6_2():
    source=Path('scripts/launch_product.py').read_text(encoding='utf-8')
    cli=Path('backend/src/deepaha/product/cli.py').read_text(encoding='utf-8')
    assert 'upgrade-sg7' in cli
    assert "command+['upgrade-sg7']" in source
    assert source.index("command+['upgrade-sg6-2']") < source.index("command+['upgrade-sg7']")


def test_sg7_1_upgrade_deactivates_v1_twins_but_preserves_history_and_requires_v2_regeneration(svc,tmp_path):
    from deepaha.product.models import LabTwin, Meta
    from deepaha.product.upgrade import upgrade_opportunity_lab
    from sqlalchemy import select
    # Simulate an accepted 3.7.0 database with one active V1 twin.
    with svc.db.tx() as db:
        meta=db.get(Meta,'opportunity_lab_schema_version');meta.value='1'
        db.add(LabTwin(twin_key='OLD-V1',version=1,label='历史V1',archetype='历史',profile={'education':'本科'},profile_hash='oldhash',active=True))
    backup=tmp_path/'before-sg7-1.zip'
    result=upgrade_opportunity_lab(svc,backup)
    assert result['backup_verified'] is True and backup.exists()
    assert result['opportunity_lab_schema_version']=='2'
    assert result['historical_twins_deactivated']==1
    assert result['v2_twin_generation_required'] is True
    assert result['production_facts_modified'] is False and result['wma_called'] is False
    with svc.db.tx(False) as db:
        meta=db.get(Meta,'opportunity_lab_schema_version')
        old=db.scalar(select(LabTwin).where(LabTwin.twin_key=='OLD-V1',LabTwin.version==1))
        assert meta.value=='2' and old is not None and old.active is False
    seeded=svc.lab_seed_twins(actor='operator')
    assert seeded['version']==2 and seeded['total']==100
    assert svc.lab_twins(actor='operator',limit=100)['total']==100
