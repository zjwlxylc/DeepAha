"""Executable SQL contract fixture, not proof of original R2 integration."""
from contextlib import contextmanager
from types import ModuleType,SimpleNamespace
import sys
import pytest
from sqlalchemy import create_engine,String,Integer
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column,Session
from deepaha_membership.integration import ProductPort
from deepaha_membership.errors import DomainError

class Base(DeclarativeBase):pass
class Identity(Base):
    __tablename__='core_identity_fixture'
    id:Mapped[int]=mapped_column(primary_key=True)
    source_id:Mapped[str]=mapped_column(String)
    opportunity_id:Mapped[str]=mapped_column(String)
class Opportunity(Base):
    __tablename__='core_opportunity_fixture'
    opportunity_id:Mapped[str]=mapped_column(primary_key=True)
class CatalogTarget(Base):
    __tablename__='core_target_fixture'
    id:Mapped[str]=mapped_column(primary_key=True)
    opportunity_id:Mapped[str]=mapped_column(String)
    status:Mapped[str]=mapped_column(String)
    created_at:Mapped[str]=mapped_column(String)
class Meta(Base):
    __tablename__='core_meta_fixture'
    key:Mapped[str]=mapped_column(primary_key=True)
    value:Mapped[str]=mapped_column(String)

@pytest.fixture
def projection(tmp_path,monkeypatch):
    models=ModuleType('deepaha.product.models')
    for c in (Identity,Opportunity,CatalogTarget,Meta):setattr(models,c.__name__,c)
    monkeypatch.setitem(sys.modules,'deepaha',ModuleType('deepaha'))
    monkeypatch.setitem(sys.modules,'deepaha.product',ModuleType('deepaha.product'))
    monkeypatch.setitem(sys.modules,'deepaha.product.models',models)
    engine=create_engine('sqlite:///'+str(tmp_path/'projection.db'));Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Meta(key='catalog_revision',value='2'),Opportunity(opportunity_id='a'),Opportunity(opportunity_id='b'),Identity(id=1,source_id='one',opportunity_id='a'),Identity(id=2,source_id='one',opportunity_id='a'),Identity(id=3,source_id='two',opportunity_id='b'),CatalogTarget(id='public1',opportunity_id='a',status='CURRENT',created_at='2026-09-21'),CatalogTarget(id='draft1',opportunity_id='a',status='DRAFT',created_at='2026-09-22'),CatalogTarget(id='public2',opportunity_id='b',status='CURRENT',created_at='2026-09-21')]);s.commit()
    @contextmanager
    def tx(write=False):
        with Session(engine) as s:yield s
    p=SimpleNamespace(db=SimpleNamespace(tx=tx),_target=lambda t,o:dict(id=t.id,status=t.status,version='v1'))
    yield ProductPort(p,None)
    engine.dispose()

def test_exact_source_lineage_no_draft_no_duplicate(projection):
    page=projection.catalog_for_source({'source_id':'one'})
    assert page['total']==1 and [x['id'] for x in page['items']]==['public1']

def test_projection_version_mismatch_fails(projection):
    with pytest.raises(DomainError) as e:projection.catalog_for_source({'source_id':'one'},read_version=1)
    assert e.value.code=='CATALOG_CHANGED'
