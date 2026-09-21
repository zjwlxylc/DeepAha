from datetime import datetime, timezone
import importlib
import pytest
from sqlalchemy import create_engine
from deepaha_membership.db import Store

class Clock:
    def __init__(self):self.value=datetime(2026,9,21,8,0,tzinfo=timezone.utc)
    def __call__(self):return self.value

@pytest.fixture
def store(tmp_path):
    s=Store(create_engine('sqlite:///'+str(tmp_path/'member.db'),connect_args={'check_same_thread':False}),Clock())
    s.initialize()
    yield s
    s.engine.dispose()

@pytest.fixture
def commerce(store):
    try:
        C=importlib.import_module('deepaha_membership.commerce').Commerce
    except ImportError:pytest.fail('commerce implementation missing')
    c=C(store);c.seed()
    return c

def actor(name='alice',roles=()):
    try:return importlib.import_module('deepaha_membership.auth').Actor(name,frozenset(roles))
    except ImportError:pytest.fail('principal implementation missing')
