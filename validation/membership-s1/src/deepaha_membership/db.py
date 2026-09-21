"""Small explicit schema, short serialized writes; never holds locks across IO."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import uuid
from sqlalchemy import (MetaData, Table, Column, String, Text, Integer, Boolean, JSON,
                        ForeignKey, UniqueConstraint, select, update, insert, inspect)
from sqlalchemy.engine import Engine
from .periods import now, stamp
from .errors import DomainError, require

metadata = MetaData()

def table(name, *columns, **kw):
    return Table('mbr_'+name, metadata, *columns, **kw)

def col(name, kind=String(128), **kw):
    return Column(name, kind, **kw)

meta = table('meta', col('key',primary_key=True),col('value',Text,nullable=False))
mutex = table('mutex',col('id',Integer,primary_key=True),col('sequence',Integer,nullable=False))
services = table('services',col('code',primary_key=True),col('data',JSON,nullable=False),col('version',Integer,nullable=False))
plans = table('plans',col('code',primary_key=True),col('version',Integer,nullable=False),col('status',String(20),nullable=False))
revisions = table('plan_revisions',col('code',ForeignKey('mbr_plans.code'),primary_key=True),col('version',Integer,primary_key=True),col('terms',JSON,nullable=False),col('created_at',String(40),nullable=False))
orders = table('orders',col('id',primary_key=True),col('owner',index=True,nullable=False),col('plan_code',nullable=False),col('terms',JSON,nullable=False),col('state',String(32),nullable=False),col('version',Integer,nullable=False),col('amount_cents',Integer),col('note',Text,nullable=False),col('created_at',String(40),nullable=False),col('updated_at',String(40),nullable=False),col('quote_expires',String(40)),col('settlement_ref',String(128),unique=True))
grants = table('grants',col('id',primary_key=True),col('order_id',ForeignKey('mbr_orders.id'),unique=True,nullable=False),col('owner',nullable=False,index=True),col('terms',JSON,nullable=False),col('starts_at',String(40),nullable=False),col('ends_at',String(40),nullable=False),col('revoked_at',String(40)),col('revoke_note',Text),col('method',String(24),nullable=False))
idems = table('idempotency',col('actor',primary_key=True),col('action',primary_key=True),col('key',primary_key=True),col('digest',String(64),nullable=False),col('result',JSON,nullable=False))
leads = table('leads',col('id',primary_key=True),col('url',String(2048),nullable=False),col('url_hash',String(64),unique=True,nullable=False),col('name',String(200),nullable=False),col('state',String(32),nullable=False),col('version',Integer,nullable=False),col('approved_url',String(2048)),col('tier',String(32)),col('public_brief',Text),col('decision_note',Text),col('source_id'),col('collection_enabled',Boolean,nullable=False,default=False),col('created_at',String(40),nullable=False))
submissions = table('submissions',col('id',primary_key=True),col('owner',nullable=False,index=True),col('lead_id',ForeignKey('mbr_leads.id'),nullable=False),col('kind',String(24),nullable=False),col('note',Text,nullable=False),col('created_at',String(40),nullable=False),UniqueConstraint('owner','lead_id',name='mbr_submission_owner_lead'))
watches = table('watches',col('id',primary_key=True),col('owner',nullable=False,index=True),col('kind',String(12),nullable=False),col('config',JSON,nullable=False),col('enabled',Boolean,nullable=False),col('version',Integer,nullable=False),col('created_at',String(40),nullable=False),col('last_checked',String(40)),col('last_error',String(500)))
jobs = table('jobs',col('id',primary_key=True),col('watch_id',ForeignKey('mbr_watches.id'),nullable=False),col('owner',nullable=False),col('state',String(24),nullable=False),col('actor'),col('connection',String(48)),col('lease_until',String(40)),col('attempts',Integer,nullable=False),col('generation',Integer,nullable=False),col('core_task_id'),col('error',String(500)),col('created_at',String(40),nullable=False),col('updated_at',String(40),nullable=False))
notices = table('notices',col('id',primary_key=True),col('owner',nullable=False,index=True),col('key',String(256),nullable=False),col('title',String(240),nullable=False),col('body',Text,nullable=False),col('target',String(256)),col('read_at',String(40)),col('created_at',String(40),nullable=False),UniqueConstraint('owner','key',name='mbr_notice_owner_key'))
audit = table('audit',col('id',primary_key=True),col('actor',nullable=False),col('event',String(60),nullable=False),col('target',nullable=False),col('data',JSON,nullable=False),col('created_at',String(40),nullable=False))


def uid():return uuid.uuid4().hex

def row(conn, stmt):
    r=conn.execute(stmt).mappings().first()
    return dict(r) if r else None

def rows(conn,stmt):return [dict(r) for r in conn.execute(stmt).mappings()]

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class Store:
    def __init__(self, engine: Engine, clock=now):
        self.engine, self.clock = engine, clock

    def time(self):return stamp(self.clock())

    def assert_ready(self):
        present=set(inspect(self.engine).get_table_names())
        if 'mbr_meta' not in present:
            raise DomainError('订阅模块尚未初始化；请先备份并执行会员模块init',503,'SCHEMA_REQUIRED')
        require(set(metadata.tables).issubset(present),'订阅结构不完整，请停止服务并核查升级回执',503,'SCHEMA_INCOMPLETE')
        with self.engine.connect() as c:
            require(c.execute(select(mutex.c.id).where(mutex.c.id==1)).scalar()==1,'订阅写锁记录缺失，请核查升级',503,'SCHEMA_INCOMPLETE')
            version=c.execute(select(meta.c.value).where(meta.c.key=='schema_version')).scalar()
        require(version=='1','订阅模块结构版本不兼容',503,'SCHEMA_MISMATCH')

    def initialize(self):
        # Only called by explicit CLI or test/demo setup, never a HTTP request.
        if 'mbr_meta' in inspect(self.engine).get_table_names():
            self.assert_ready()
            return
        metadata.create_all(self.engine)
        with self.engine.begin() as c:
            c.execute(insert(meta).values(key='schema_version',value='1'))
            c.execute(insert(mutex).values(id=1,sequence=0))

    @contextmanager
    def read(self):
        with self.engine.connect() as c:yield c

    @contextmanager
    def write(self):
        with self.engine.begin() as c:
            if self.engine.dialect.name=='sqlite':
                c.exec_driver_sql('PRAGMA busy_timeout=8000')
            require(c.execute(update(mutex).where(mutex.c.id==1).values(sequence=mutex.c.sequence+1)).rowcount==1,'订阅写锁未初始化',503)
            yield c

    def audit(self,c,actor,event,target,data=None):
        c.execute(insert(audit).values(id=uid(),actor=actor,event=event,target=target,data=data or {},created_at=self.time()))

    def notice(self,c,owner,key,title,body='',target=None):
        existing=row(c,select(notices).where(notices.c.owner==owner,notices.c.key==key))
        if existing:return existing
        data=dict(id=uid(),owner=owner,key=key,title=title,body=body,target=target,read_at=None,created_at=self.time())
        c.execute(insert(notices).values(**data))
        return data

    def idempotent(self,c,actor,action,key,payload,fn):
        require(isinstance(key,str) and 8<=len(key)<=128,'请求标识须为8至128字符')
        old=row(c,select(idems).where(idems.c.actor==actor,idems.c.action==action,idems.c.key==key))
        hashed=digest(payload)
        if old:
            require(old['digest']==hashed,'同一请求标识对应不同内容，请重新操作',409,'IDEMPOTENCY_CONFLICT')
            return old['result']
        result=fn()
        c.execute(insert(idems).values(actor=actor,action=action,key=key,digest=hashed,result=result))
        return result
