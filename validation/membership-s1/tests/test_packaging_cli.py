from pathlib import Path
import importlib.util,importlib,zipfile,hashlib
import pytest
from sqlalchemy import create_engine,text,inspect

ROOT=Path(__file__).parents[1]

def tool():
    path=ROOT/'tools/assemble_r2.py'
    assert path.exists(),'exact-baseline assembler missing'
    spec=importlib.util.spec_from_file_location('assembler_test',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_assembler_rejects_wrong_baseline_hash(tmp_path):
    m=tool();z=tmp_path/'wrong.zip'
    with zipfile.ZipFile(z,'w') as out:out.writestr('README.md','not R2')
    with pytest.raises(ValueError,match='SHA'):m.assemble(z,tmp_path/'out.zip',ROOT)
    assert not (tmp_path/'out.zip').exists()

@pytest.mark.parametrize('name',['../escape','/absolute','C:/drive','a/../../escape','folder\\evil','a/CON.txt'])
def test_secure_extract_blocks_unsafe_path(tmp_path,name):
    m=tool();z=tmp_path/'bad.zip'
    info=zipfile.ZipInfo(name);info.filename=name  # Preserve raw backslashes on Windows too.
    with zipfile.ZipFile(z,'w') as out:out.writestr(info,'bad')
    with pytest.raises(ValueError):m.safe_extract(z,tmp_path/'extract')

def test_secure_extract_blocks_symlink(tmp_path):
    m=tool();z=tmp_path/'bad.zip';info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=0o120777<<16
    with zipfile.ZipFile(z,'w') as out:out.writestr(info,'../../outside')
    with pytest.raises(ValueError):m.safe_extract(z,tmp_path/'extract')

def test_api_patch_is_narrow_and_fail_closed():
    m=tool();source='def create_app():\n    x=1\n    mount_access(app,p,user)\n    return app\n'
    patched=m.patch_api(source)
    assert 'mount_membership(app,p,settings)' in patched
    assert patched.replace(m.HOOK,'')==source
    with pytest.raises(ValueError):m.patch_api('def something_else():\n    return 1\n')
    with pytest.raises(ValueError):m.patch_api(patched)

def test_synthetic_candidate_assembly_preserves_original_assets(tmp_path,monkeypatch):
    m=tool();z=tmp_path/'fixture.zip';target='R2/backend/src/deepaha/product/api.py'
    with zipfile.ZipFile(z,'w') as out:
        out.writestr(target,'def create_app():\n    mount_access(app,p,user)\n    return app\n')
        out.writestr('R2/CHANGESET_MOBILE_R2.json','{"fixture":true}')
        out.writestr('R2/web/public/poster.svg','<svg>ORIGINAL</svg>')
    monkeypatch.setattr(m,'EXPECTED_SHA',hashlib.sha256(z.read_bytes()).hexdigest())
    result=m.assemble(z,tmp_path/'candidate.zip',ROOT)
    assert result['status']=='UNVERIFIED_INTEGRATION_CANDIDATE'
    assert len(result['modified_baseline_files'])==1
    with zipfile.ZipFile(tmp_path/'candidate.zip') as out:
        assert out.read('R2/web/public/poster.svg')==b'<svg>ORIGINAL</svg>'
        assert out.testzip() is None
        assert 'R2/backend/src/deepaha_membership/api.py' in out.namelist()

def test_cli_backup_precedes_init_and_preserves_existing_table(tmp_path):
    try:M=importlib.import_module('deepaha_membership.cli')
    except ImportError:pytest.fail('explicit init CLI missing')
    db=tmp_path/'core.db';engine=create_engine('sqlite:///'+str(db))
    with engine.begin() as c:c.execute(text('CREATE TABLE existing_core(id int)'));c.execute(text('INSERT INTO existing_core VALUES (1)'))
    backup=tmp_path/'backup.db'
    receipt=M.initialize_database(str(engine.url),backup)
    assert backup.exists() and (tmp_path/'backup.db.manifest.json').exists()
    assert 'mbr_plans' in inspect(engine).get_table_names()
    with engine.connect() as c:assert c.execute(text('SELECT id FROM existing_core')).scalar()==1
    old=create_engine('sqlite:///'+str(backup));assert 'mbr_plans' not in inspect(old).get_table_names()
    assert receipt['database_driver']=='sqlite'
    old.dispose();engine.dispose()

def test_cli_will_not_overwrite_backup(tmp_path):
    try:M=importlib.import_module('deepaha_membership.cli')
    except ImportError:pytest.fail('explicit init CLI missing')
    db=tmp_path/'core.db';engine=create_engine('sqlite:///'+str(db))
    with engine.begin() as c:c.execute(text('CREATE TABLE existing_core(id int)'))
    backup=tmp_path/'backup.db';backup.write_bytes(b'KEEP')
    with pytest.raises((ValueError,FileExistsError)):M.initialize_database(str(engine.url),backup)
    assert backup.read_bytes()==b'KEEP'
    assert 'mbr_meta' not in inspect(engine).get_table_names()
