"""Run real R3 host transactions on a dedicated PostgreSQL test database only."""
import pytest
from fastapi.testclient import TestClient
from .test_experience_postgres import pg
from . import test_services_r3 as cases

@pytest.mark.parametrize('case',[
 'test_member_routes_share_real_auth_roles_and_csrf',
 'test_real_trial_changes_entitlements_not_role_or_free_catalog',
 'test_messages_merge_badges_batch_read_and_do_not_leak',
 'test_export_and_erase_cover_member_private_data_preserve_contract',
 'test_free_site_enters_review_without_publishing',
 'test_runtime_settings_explicit_versioned_authorization',
])
def test_r3_real_postgres_host_transactions(pg,case):
 from deepaha.product.api import create_app
 from deepaha.product.config import Settings
 import inspect
 for name,roles in [('operator',['operator']),('reviewer',['reviewer']),('reader',['user'])]:
  pg.create_account(name,'long-password-123',roles)
 pg.test_source=pg.add_source('PostgreSQL synthetic source','https://research.example.org/',actor='operator')['id']
 app=create_app(Settings(database_url=pg.database_url,data_dir=pg.object_root.parent,public_catalog=True,allowed_hosts=['testserver']),product=pg)
 with TestClient(app) as client:
  fn=getattr(cases,case)
  fn(**{key:client if key=='client' else pg for key in inspect.signature(fn).parameters})
