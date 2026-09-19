from sqlalchemy import select

from .test_contract import svc
from .test_eligibility import _zip, approve


def _bundle():
    import json
    official='https://research.example.org/notices/sg6-2-upgrade'
    root={
        'opportunity_name':'SG6.2升级样本','publish_unit':'海湾研究中心','opportunity_type':'PUBLIC_INSTITUTION_JOB','official_url':official,
        'units':[{'id':'g1','name':'测试单位','positions':[{'id':'p1','name':'测试岗','code':'Q01','facts':[
            {'field':'education','value':'本科及以上','status':'CONFIRMED','evidence':[{'artifact_id':'a1','quote':'education：本科及以上','locator':{'line':1}}]},
            {'field':'degree','value':'学士及以上','status':'CONFIRMED','evidence':[{'artifact_id':'a1','quote':'degree：学士及以上','locator':{'line':2}}]},
        ]}]}],
    }
    files={
        'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),
        'evidence.json':json.dumps({'artifacts':[{'artifact_id':'a1','local_path':'artifacts/notice.txt','url':official}]},ensure_ascii=False).encode(),
        'report.md':b'# sg6.2 upgrade',
        'artifacts/notice.txt':'education：本科及以上\ndegree：学士及以上'.encode(),
    }
    return _zip(files)


def test_sg6_2_upgrade_is_backup_first_adds_only_derived_compiler_metadata_and_is_idempotent(svc,tmp_path):
    from deepaha.product.models import CatalogTarget, Meta
    from deepaha.product.upgrade import upgrade_qualification_compiler

    oid=approve(svc,_bundle(),'sg6-2-upgrade-source')
    public_id=svc.catalog(limit=20)['items'][0]['id']
    with svc.db.tx() as s:
        target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==public_id,CatalogTarget.status=='CURRENT'))
        body=dict(target.content);body.pop('qualification_compiler',None);target.content=body

    backup=tmp_path/'before-sg6-2.zip'
    first=upgrade_qualification_compiler(svc,backup)
    assert first['backup_verified'] is True
    assert first['targets_refreshed']==1
    assert first['data_modified'] is True
    assert backup.exists()
    with svc.db.tx(False) as s:
        target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==public_id,CatalogTarget.status=='CURRENT'))
        meta=(target.content or {}).get('qualification_compiler') or {}
        assert meta['version']==1
        assert meta['canonical_condition_count']==2
        assert meta['deterministic_condition_count']==2
        assert set(meta['canonical_types'])=={'EDUCATION_MIN','DEGREE_MIN'}
        assert s.get(Meta,'qualification_compiler_version').value=='1'

    unused=tmp_path/'unused-second.zip'
    second=upgrade_qualification_compiler(svc,unused)
    assert second['already_current'] is True
    assert second['data_modified'] is False
    assert not unused.exists()


def test_newly_projected_targets_receive_sg6_2_compiler_metadata(svc):
    from deepaha.product.models import CatalogTarget
    approve(svc,_bundle(),'sg6-2-new-projection')
    with svc.db.tx(False) as s:
        target=s.scalar(select(CatalogTarget).where(CatalogTarget.status=='CURRENT').order_by(CatalogTarget.created_at.desc()))
        meta=(target.content or {}).get('qualification_compiler') or {}
        assert meta['version']==1
        assert meta['canonical_condition_count']==2
        assert meta['deterministic_condition_count']==2


def test_windows_launcher_runs_sg6_2_refresh_after_sg6_upgrade():
    from pathlib import Path
    cli=Path('backend/src/deepaha/product/cli.py').read_text(encoding='utf-8')
    launcher=Path('scripts/launch_product.py').read_text(encoding='utf-8')
    assert 'upgrade-sg6-2' in cli
    assert "command+['upgrade-sg6-2']" in launcher
    assert launcher.index("command+['upgrade-sg6']") < launcher.index("command+['upgrade-sg6-2']")
