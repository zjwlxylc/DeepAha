from contextlib import contextmanager
from sqlalchemy import create_engine, event, select, text, inspect
from sqlalchemy.orm import Session
from .models import Base, Meta, LAB_TABLE_NAMES
from .errors import Problem

class Database:
    def __init__(self, url):
        self.url=url
        kw={'pool_pre_ping':True}
        if url.startswith('sqlite'):
            kw['connect_args']={'check_same_thread':False,'timeout':30}
        self.engine=create_engine(url,**kw)
        if self.engine.dialect.name=='sqlite':
            @event.listens_for(self.engine,'connect')
            def setup(conn,_):
                conn.execute('PRAGMA foreign_keys=ON')
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA busy_timeout=30000')
    def initialize(self, allow_existing_upgrade=False):
        # CREATE missing only. Existing rc2 stores require an explicit backup-first SG1 upgrade.
        existing=set(inspect(self.engine).get_table_names())
        actionable={'product_opportunity_units','product_catalog_targets','product_target_actions','product_target_feedback','product_target_notices'}
        action_loop={'product_target_action_events','product_feedback_candidates'}
        if 'product_meta' in existing and not actionable.issubset(existing) and not allow_existing_upgrade:
            raise Problem('行动目标数据结构尚未升级。停服务后运行：python -m deepaha.product.cli upgrade-sg1',409,'ACTIONABLE_UPGRADE_REQUIRED')
        if 'product_meta' in existing and actionable.issubset(existing) and not action_loop.issubset(existing) and not allow_existing_upgrade:
            raise Problem('SG6行动闭环数据结构尚未升级。停服务后运行：python -m deepaha.product.cli upgrade-sg6',409,'ACTION_LOOP_UPGRADE_REQUIRED')
        if 'product_meta' in existing and action_loop.issubset(existing) and not LAB_TABLE_NAMES.issubset(existing) and not allow_existing_upgrade:
            raise Problem('SG7机会实验室数据结构尚未升级。停服务后运行：python -m deepaha.product.cli upgrade-sg7',409,'OPPORTUNITY_LAB_UPGRADE_REQUIRED')
        Base.metadata.create_all(self.engine)
        with self.tx() as s:
            row=s.get(Meta,'schema_version')
            if row and row.value!='1':raise Problem('数据结构版本不兼容',409)
            if not row:s.add(Meta(key='schema_version',value='1'))
            if not s.get(Meta,'catalog_revision'):s.add(Meta(key='catalog_revision',value='0'))
            av=s.get(Meta,'actionable_schema_version')
            if av and av.value!='2':raise Problem('行动目标数据结构版本不兼容',409)
            if not av:s.add(Meta(key='actionable_schema_version',value='2'))
            lv=s.get(Meta,'action_loop_schema_version')
            if lv and lv.value!='1':raise Problem('行动闭环数据结构版本不兼容',409)
            if not lv:s.add(Meta(key='action_loop_schema_version',value='1'))
            lab=s.get(Meta,'opportunity_lab_schema_version')
            if lab and lab.value!='2':
                if not (allow_existing_upgrade and lab.value=='1'):
                    raise Problem('SG7机会实验室数据结构版本不兼容；3.7.0请先运行upgrade-sg7升级到SG7.1',409)
            if not lab:s.add(Meta(key='opportunity_lab_schema_version',value='2'))
    @contextmanager
    def tx(self,write=True):
        with Session(self.engine,expire_on_commit=False) as s:
            try:
                if write and self.engine.dialect.name=='sqlite':s.execute(text('BEGIN IMMEDIATE'))
                if write and self.engine.dialect.name=='postgresql':
                    # Short domain writes serialized in this release. Remote work never holds this lock.
                    s.execute(text('SELECT pg_advisory_xact_lock(73489321)'))
                yield s
                if write:s.commit()
            except Exception:
                s.rollback()
                raise
    def tick(self,s):
        r=s.get(Meta,'catalog_revision');r.value=str(int(r.value)+1)
        return int(r.value)
