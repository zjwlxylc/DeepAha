"""Reference research-staging repositories, NOT the production Source Registry.

Only SQLite uses the local computer. PostgreSQL uses a supplied DSN and explicit
initialization. Both adapters use the same queries and immutable revision model.
A host-project repository can implement the same transaction interface and reuse
existing DeepAha models. Reference adapters cannot label themselves PRODUCTION.
"""
from __future__ import annotations
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from .contract import canonical_json, parse_json
from .errors import ImporterError

SCHEMA_VERSION = '1'
DDL = [
    '''CREATE TABLE IF NOT EXISTS scout_import_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1), schema_version TEXT NOT NULL,
        target_id TEXT NOT NULL UNIQUE, generation INTEGER NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS scout_import_batch (
        batch_id TEXT PRIMARY KEY, producer TEXT NOT NULL, run_key TEXT NOT NULL,
        package_hash TEXT NOT NULL, raw_hash TEXT NOT NULL, raw_handoff BLOB NOT NULL,
        actor TEXT NOT NULL, created_at TEXT NOT NULL, receipt_json TEXT NOT NULL,
        UNIQUE(producer, run_key))''',
    '''CREATE TABLE IF NOT EXISTS scout_import_asset (
        asset_id TEXT PRIMARY KEY, producer TEXT NOT NULL, kind TEXT NOT NULL,
        asset_key TEXT NOT NULL, identity_hash TEXT, external_revision TEXT,
        system_revision INTEGER NOT NULL CHECK(system_revision > 0),
        content_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
        UNIQUE(producer, kind, asset_key), UNIQUE(producer, kind, identity_hash))''',
    '''CREATE TABLE IF NOT EXISTS scout_import_alias (
        producer TEXT NOT NULL, kind TEXT NOT NULL, alias_key TEXT NOT NULL,
        asset_id TEXT NOT NULL REFERENCES scout_import_asset(asset_id),
        PRIMARY KEY(producer, kind, alias_key))''',
    '''CREATE TABLE IF NOT EXISTS scout_import_revision (
        asset_id TEXT NOT NULL REFERENCES scout_import_asset(asset_id),
        system_revision INTEGER NOT NULL, batch_id TEXT NOT NULL REFERENCES scout_import_batch(batch_id),
        external_revision TEXT, content_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
        PRIMARY KEY(asset_id, system_revision))''',
    '''CREATE TABLE IF NOT EXISTS scout_import_file (
        batch_id TEXT NOT NULL REFERENCES scout_import_batch(batch_id), name TEXT NOT NULL,
        sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, content BLOB NOT NULL,
        PRIMARY KEY(batch_id, name))''',
    '''CREATE TABLE IF NOT EXISTS scout_import_link (
        batch_id TEXT NOT NULL REFERENCES scout_import_batch(batch_id),
        ref_kind TEXT NOT NULL, ref_key TEXT NOT NULL,
        asset_id TEXT NOT NULL REFERENCES scout_import_asset(asset_id),
        PRIMARY KEY(batch_id, ref_kind, ref_key))''',
]


def encode(value) -> str:
    return canonical_json(value).decode('utf-8')


def decode(value: str):
    return parse_json(value.encode('utf-8'), 96 * 1024 * 1024)


class Transaction:
    def __init__(self, connection, dialect: str):
        self.connection, self.dialect = connection, dialect

    def execute(self, sql: str, params=()):
        if self.dialect == 'postgres': sql = sql.replace('?', '%s')
        return self.connection.execute(sql, params)

    def meta(self):
        row = self.execute('SELECT * FROM scout_import_meta WHERE singleton=1').fetchone()
        if row is None or row['schema_version'] != SCHEMA_VERSION:
            raise ImporterError('SCHEMA_NOT_READY', '导入暂存库尚未初始化或版本不兼容。', 503)
        return dict(row)

    def snapshot(self, producer):
        records = [dict(r) for r in self.execute('SELECT * FROM scout_import_asset WHERE producer=?', (producer,)).fetchall()]
        for record in records: record['payload'] = decode(record.pop('payload_json'))
        aliases = {(r['kind'], r['alias_key']): r['asset_id'] for r in self.execute(
            'SELECT * FROM scout_import_alias WHERE producer=?', (producer,)).fetchall()}
        return records, aliases

    def batch(self, producer, run_key):
        row = self.execute('SELECT * FROM scout_import_batch WHERE producer=? AND run_key=?', (producer, run_key)).fetchone()
        return None if row is None else dict(row)

    def insert_batch(self, batch_id, producer, package, actor, created_at):
        self.execute('''INSERT INTO scout_import_batch
          (batch_id, producer, run_key, package_hash, raw_hash, raw_handoff, actor, created_at, receipt_json)
          VALUES (?,?,?,?,?,?,?,?,?)''',
          (batch_id, producer, package.run_key, package.package_hash, package.sha256,
           package.raw, actor, created_at, '{}'))

    def save_asset(self, record: dict, batch_id: str, create: bool):
        r = record
        if create:
            self.execute('''INSERT INTO scout_import_asset
              (asset_id, producer, kind, asset_key, identity_hash, external_revision,
               system_revision, content_hash, payload_json) VALUES (?,?,?,?,?,?,?,?,?)''',
              (r['asset_id'], r['producer'], r['kind'], r['asset_key'], r['identity_hash'],
               r['external_revision'], r['system_revision'], r['content_hash'], encode(r['payload'])))
        else:
            self.execute('''UPDATE scout_import_asset SET identity_hash=?, external_revision=?,
              system_revision=?, content_hash=?, payload_json=? WHERE asset_id=?''',
              (r['identity_hash'], r['external_revision'], r['system_revision'], r['content_hash'],
               encode(r['payload']), r['asset_id']))
        self.execute('''INSERT INTO scout_import_revision
          (asset_id, system_revision, batch_id, external_revision, content_hash, payload_json)
          VALUES (?,?,?,?,?,?)''',
          (r['asset_id'], r['system_revision'], batch_id, r['external_revision'], r['content_hash'], encode(r['payload'])))

    def add_alias(self, producer, kind, key, asset_id):
        existing = self.execute('SELECT asset_id FROM scout_import_alias WHERE producer=? AND kind=? AND alias_key=?',
                                (producer, kind, key)).fetchone()
        if existing is not None:
            if existing['asset_id'] != asset_id:
                raise ImporterError('ALIAS_CONFLICT', '引用别名已有其他归属。', 409)
            return
        self.execute('INSERT INTO scout_import_alias (producer,kind,alias_key,asset_id) VALUES (?,?,?,?)',
                     (producer, kind, key, asset_id))

    def add_file(self, batch_id, name, blob, sha256):
        self.execute('INSERT INTO scout_import_file (batch_id,name,sha256,size_bytes,content) VALUES (?,?,?,?,?)',
                     (batch_id, name, sha256, len(blob), blob))

    def add_link(self, batch_id, kind, key, asset_id):
        self.execute('INSERT INTO scout_import_link (batch_id,ref_kind,ref_key,asset_id) VALUES (?,?,?,?)',
                     (batch_id, kind, key, asset_id))

    def finalize(self, batch_id, receipt):
        self.execute('UPDATE scout_import_batch SET receipt_json=? WHERE batch_id=?', (encode(receipt), batch_id))
        self.execute('UPDATE scout_import_meta SET generation=generation+1 WHERE singleton=1')


class SQLiteRepository:
    reference_backend = True
    dialect = 'sqlite'

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def initialize(self):
        """Explicit setup, never invoked by preview/commit implicitly."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON'); db.execute('BEGIN IMMEDIATE')
            for statement in DDL: db.execute(statement)
            row = db.execute('SELECT schema_version FROM scout_import_meta WHERE singleton=1').fetchone()
            if row is None:
                db.execute('INSERT INTO scout_import_meta VALUES (1,?,?,0)', (SCHEMA_VERSION, str(uuid.uuid4())))
            elif row[0] != SCHEMA_VERSION:
                raise ImporterError('SCHEMA_MISMATCH', '已有数据库版本不兼容，拒绝自动改写。', 409)
            db.commit()
        except Exception:
            db.rollback(); raise
        finally:
            db.close()

    @contextmanager
    def transaction(self, write=False):
        if not self.path.is_file():
            raise ImporterError('SCHEMA_NOT_READY', '请先显式初始化演练库，或连接已配置的服务器。', 503)
        mode = 'rw' if write else 'ro'
        db = sqlite3.connect(self.path.as_uri() + '?mode=' + mode, uri=True, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            if not write: db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            tx = Transaction(db, self.dialect); tx.meta()
            yield tx
            if write: db.commit()
            else: db.rollback()
        except Exception:
            db.rollback(); raise
        finally:
            db.close()


class PostgresRepository:
    """Optional complete PostgreSQL reference-staging adapter. Requires psycopg3.

    Not tested against a live PostgreSQL instance in this delivery. Do not deploy
    as a parallel source registry. Codex must map/reuse the actual project tables.
    """
    reference_backend = True
    dialect = 'postgres'

    def __init__(self, dsn: str):
        self._dsn = dsn

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise ImporterError('DRIVER_UNAVAILABLE', 'PostgreSQL 适配需要安装 psycopg3。', 503) from exc
        return psycopg.connect(self._dsn, autocommit=True, row_factory=dict_row, connect_timeout=10)

    def initialize(self):
        with self._connect() as db:
            db.execute('BEGIN')
            try:
                for statement in DDL: db.execute(statement.replace(' BLOB ', ' BYTEA '))
                db.execute('''INSERT INTO scout_import_meta VALUES (1,%s,%s,0)
                              ON CONFLICT (singleton) DO NOTHING''', (SCHEMA_VERSION, str(uuid.uuid4())))
                Transaction(db, self.dialect).meta()
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK'); raise

    @contextmanager
    def transaction(self, write=False):
        with self._connect() as db:
            db.execute('BEGIN' if write else 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            try:
                if write:
                    # Serialize small-batch imports; no guessed distributed lock service.
                    db.execute('SELECT generation FROM scout_import_meta WHERE singleton=1 FOR UPDATE')
                tx = Transaction(db, self.dialect); tx.meta()
                yield tx
                db.execute('COMMIT' if write else 'ROLLBACK')
            except Exception:
                db.execute('ROLLBACK'); raise
