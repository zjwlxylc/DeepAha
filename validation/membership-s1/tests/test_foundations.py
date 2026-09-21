import importlib
from datetime import datetime, timezone
import pytest


def mod(name):
    try:
        return importlib.import_module('deepaha_membership.' + name)
    except ImportError:
        pytest.fail(f'{name} implementation is not present yet')


@pytest.mark.parametrize('start,months,expected',[
 ('2026-01-31T02:00:00+00:00',1,'2026-02-28T02:00:00+00:00'),
 ('2024-02-29T03:00:00+00:00',12,'2025-02-28T03:00:00+00:00'),
 ('2026-09-21T10:20:00+00:00',2,'2026-11-21T10:20:00+00:00'),
 ('2026-01-30T18:00:00+00:00',1,'2026-02-27T18:00:00+00:00'),
])
def test_calendar_term_uses_shanghai_local_date(start,months,expected):
    assert mod('periods').add_months(datetime.fromisoformat(start), months).isoformat()==expected


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):mod('periods').add_months(datetime(2026,1,1),2)


@pytest.mark.parametrize('url',[
 'http://127.0.0.1','http://[::1]/','http://169.254.169.254/',
 'file:///etc/passwd','javascript:alert(1)','https://u:p@example.com',
 'http://localhost/','http://a.internal/','http://a.local/',
 'http://2130706433/','http://0177.0.0.1/','http://0x7f000001/',
 'https://example.com:8080/','https://example.com/?token=secret',
 'https://example.com/\nfoo','https://example.com\\@evil.com',
 'https://example.com/?SESSIONID=secret','https://%31%32%37.0.0.1/',
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):mod('urls').canonicalize(url)


def test_normalization_preserves_meaningful_query_and_case_path():
    assert mod('urls').canonicalize('HTTPS://Example.COM:443/Jobs?id=3&utm_source=x#top')=='https://example.com/Jobs?id=3'


def test_dns_guard_checks_every_address():
    with pytest.raises(ValueError):
        mod('urls').validate_public_dns('https://example.com/',resolver=lambda host:['93.184.216.34','10.0.0.1'])
    assert mod('urls').validate_public_dns('https://example.com/',resolver=lambda host:['93.184.216.34'])==['93.184.216.34']


def test_read_does_not_initialize_database(tmp_path):
    from sqlalchemy import create_engine,inspect
    engine=create_engine('sqlite:///'+str(tmp_path/'empty.db'))
    store=mod('db').Store(engine)
    assert not inspect(engine).get_table_names()
    with pytest.raises(Exception):store.assert_ready()
    store.initialize()
    store.assert_ready()
    names=inspect(engine).get_table_names()
    assert names and all(n.startswith('mbr_') for n in names)
    store.initialize()

def test_partial_membership_schema_fails_readiness(store):
    from sqlalchemy import text
    from deepaha_membership.errors import DomainError
    with store.engine.begin() as c:c.execute(text('DROP TABLE mbr_jobs'))
    with pytest.raises(DomainError):store.assert_ready()

def test_missing_membership_mutex_fails_readiness(store):
    from sqlalchemy import text
    from deepaha_membership.errors import DomainError
    with store.engine.begin() as c:c.execute(text('DELETE FROM mbr_mutex'))
    with pytest.raises(DomainError):store.assert_ready()
