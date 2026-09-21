"""SG8-A production deployment helpers.

This module deliberately keeps deployment authority outside the application:
- it never edits nginx/systemd or server secrets;
- PostgreSQL migration only accepts an already verified DeepAha SQLite backup;
- migration refuses a non-empty destination database/object store;
- WMA credentials are never copied from a local backup.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Engine

from .backup import restore_backup, verify_backup
from .config import ConnectionConfig, Settings
from .db import Database
from .errors import Problem
from .models import Account, Base, Meta
# Register the additive Scout tables in the shared SQLAlchemy metadata before
# migration/table validation walks Base.metadata.
from . import scout_models as _scout_models  # noqa: F401

RELEASE = "3.8.0-rc1"
REQUIRED_META = {
    "schema_version": "1",
    "actionable_schema_version": "2",
    "action_loop_schema_version": "1",
    "opportunity_lab_schema_version": "2",
}


def _all_tables():
    from deepaha_membership.db import metadata as membership_metadata
    return list(Base.metadata.sorted_tables)+list(membership_metadata.sorted_tables)


def _table_names() -> list[str]:
    return [table.name for table in _all_tables()]


def _normal(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): _normal(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normal(v) for v in value]
    return value


def _table_fingerprint(engine: Engine, table) -> tuple[int, str]:
    pk = list(table.primary_key.columns)
    statement = select(table)
    if pk:
        statement = statement.order_by(*pk)
    digest = hashlib.sha256()
    count = 0
    with engine.connect() as connection:
        for row in connection.execute(statement).mappings():
            payload = {column.name: _normal(row[column.name]) for column in table.columns}
            digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
            digest.update(b"\n")
            count += 1
    return count, digest.hexdigest()


def _objects_fingerprint(root: Path) -> tuple[int, str]:
    root = Path(root)
    digest = hashlib.sha256()
    count = 0
    if not root.exists():
        return 0, digest.hexdigest()
    for path in sorted((p for p in root.rglob("*") if p.is_file() and ".locks" not in p.parts), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(relative.encode("utf-8")); digest.update(b"\0")
        digest.update(file_digest.encode("ascii")); digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def _destination_has_rows(engine: Engine) -> list[str]:
    existing = set(inspect(engine).get_table_names())
    occupied: list[str] = []
    with engine.connect() as connection:
        for table in _all_tables():
            if table.name not in existing:
                continue
            if connection.execute(select(func.count()).select_from(table)).scalar_one() > 0:
                occupied.append(table.name)
    return occupied


def _copy_database(source_url: str, destination_url: str, *, require_postgres: bool = True) -> dict:
    source = Database(source_url)
    destination = Database(destination_url)
    try:
        if source.engine.dialect.name != "sqlite":
            raise Problem("迁移源必须是DeepAha SQLite备份", 409, "MIGRATION_SOURCE")
        if require_postgres and destination.engine.dialect.name != "postgresql":
            raise Problem("正式迁移目标必须是PostgreSQL", 409, "MIGRATION_TARGET")
        expected = set(_table_names())
        source_tables = set(inspect(source.engine).get_table_names())
        missing = sorted(expected - source_tables)
        if missing:
            raise Problem("备份缺少当前版本数据表：" + ", ".join(missing[:8]), 409, "MIGRATION_SCHEMA")
        occupied = _destination_has_rows(destination.engine)
        if occupied:
            raise Problem("目标数据库不是空库，拒绝覆盖：" + ", ".join(occupied[:8]), 409, "MIGRATION_NONEMPTY")

        Base.metadata.create_all(destination.engine)
        from deepaha_membership.db import metadata as membership_metadata
        membership_metadata.create_all(destination.engine)
        copied: dict[str, int] = {}
        with source.engine.connect() as source_connection, destination.engine.begin() as destination_connection:
            for table in _all_tables():
                rows = source_connection.execute(select(table)).mappings()
                batch: list[dict] = []
                total = 0
                for row in rows:
                    item = dict(row)
                    # SQLite loses timezone offsets for DateTime(timezone=True).
                    # Treat stored naive datetimes as UTC, matching DeepAha now().
                    for column in table.columns:
                        value = item.get(column.name)
                        if isinstance(value, datetime) and value.tzinfo is None:
                            item[column.name] = value.replace(tzinfo=timezone.utc)
                    batch.append(item)
                    if len(batch) >= 500:
                        destination_connection.execute(table.insert(), batch)
                        total += len(batch); batch.clear()
                if batch:
                    destination_connection.execute(table.insert(), batch)
                    total += len(batch)
                copied[table.name] = total

        fingerprints = {}
        for table in _all_tables():
            source_count, source_digest = _table_fingerprint(source.engine, table)
            destination_count, destination_digest = _table_fingerprint(destination.engine, table)
            if source_count != destination_count or source_digest != destination_digest:
                raise Problem("迁移后数据校验不一致：" + table.name, 503, "MIGRATION_VERIFY")
            fingerprints[table.name] = {"rows": source_count, "sha256": source_digest}
        return {"tables": copied, "fingerprints": fingerprints}
    finally:
        source.engine.dispose(); destination.engine.dispose()


def migrate_sqlite_backup(
    backup_file: Path,
    destination_url: str,
    destination_object_root: Path,
    *,
    require_postgres: bool = True,
) -> dict:
    """Migrate one SG7.2-compatible SQLite backup into an empty database/store.

    The existing backup restore path revokes all browser sessions and strips the
    worker heartbeat before the database is copied. This is intentional: a
    production deployment must never inherit a local browser session or worker.
    """
    backup_file = Path(backup_file).resolve()
    destination_object_root = Path(destination_object_root).resolve()
    verify_backup(backup_file)

    existing_files = [p for p in destination_object_root.rglob("*") if p.is_file()] if destination_object_root.exists() else []
    if existing_files:
        raise Problem("目标原件目录不是空目录，拒绝覆盖", 409, "MIGRATION_OBJECTS_NONEMPTY")

    with tempfile.TemporaryDirectory(prefix="deepaha-sg8a-migrate-") as temporary:
        restored = Path(temporary) / "restored"
        restore_backup(backup_file, restored)
        source_db = restored / "deepaha.db"
        source_objects = restored / "objects"
        database = _copy_database("sqlite:///" + str(source_db), destination_url, require_postgres=require_postgres)

        source_object_count, source_object_digest = _objects_fingerprint(source_objects)
        destination_object_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in sorted(source_objects.rglob("*")):
            if not path.is_file() or ".locks" in path.parts:
                continue
            relative = path.relative_to(source_objects)
            target = destination_object_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise Problem("目标原件目录发生并发写入，停止迁移", 409, "MIGRATION_OBJECT_RACE")
            shutil.copy2(path, target)
        # The write-once store expects its lock directory but lock files are not backup data.
        (destination_object_root / "deepaha-raw" / ".locks").mkdir(parents=True, exist_ok=True)
        destination_object_count, destination_object_digest = _objects_fingerprint(destination_object_root)
        if (source_object_count, source_object_digest) != (destination_object_count, destination_object_digest):
            raise Problem("迁移后原件校验不一致", 503, "MIGRATION_OBJECT_VERIFY")

    return {
        "release": RELEASE,
        "migrated": True,
        "source_backup": str(backup_file),
        "sessions_revoked": True,
        "credentials_migrated": False,
        "database": database,
        "objects": {"files": source_object_count, "sha256": source_object_digest},
    }


def deployment_check(settings: Settings, *, require_account: bool = True) -> dict:
    """Read-only production readiness check; no WMA call and no schema change."""
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: Any = None, *, required: bool = True):
        checks.append({"name": name, "ok": bool(ok), "required": required, "detail": detail})

    record("mode_production", settings.mode == "production", settings.mode)
    record("secure_cookie", settings.secure_cookie, settings.secure_cookie)
    record("explicit_hosts", bool(settings.allowed_hosts) and "*" not in settings.allowed_hosts, settings.allowed_hosts)
    record("https_origins", bool(settings.origins) and all(origin.startswith("https://") for origin in settings.origins), settings.origins)
    record("postgresql_url", settings.database_url.startswith("postgresql"), settings.database_url.split(":", 1)[0] if settings.database_url else "")

    database = None
    try:
        database = Database(settings.database_url)
        dialect = database.engine.dialect.name
        record("database_dialect", dialect == "postgresql", dialect)
        inspector = inspect(database.engine)
        existing = set(inspector.get_table_names())
        required_tables = set(_table_names())
        missing = sorted(required_tables - existing)
        record("schema_tables", not missing, {"required": len(required_tables), "missing": missing})
        meta_values = {}
        active_accounts = 0
        if not missing and "product_meta" in existing:
            with database.tx(False) as session:
                meta_values = {key: (session.get(Meta, key).value if session.get(Meta, key) else None) for key in REQUIRED_META}
                active_accounts = session.scalar(select(func.count()).select_from(Account).where(Account.active.is_(True))) or 0
        try:
            from deepaha_membership.db import Store
            Store(database.engine).assert_ready()
            record("services_schema",True,{"version":"1"})
        except Exception:
            record("services_schema",False,"upgrade-services required")
        record("schema_versions", all(meta_values.get(k) == v for k, v in REQUIRED_META.items()), meta_values)
        record("active_account", (active_accounts > 0) or not require_account, active_accounts)
    except Exception as exc:  # Deployment check must summarize instead of leaking a stack trace.
        record("database_connectivity", False, type(exc).__name__)
    finally:
        if database is not None:
            database.engine.dispose()

    data_dir = settings.data_dir
    try:
        writable = data_dir.is_dir() and os.access(data_dir, os.R_OK | os.W_OK | os.X_OK)
    except OSError:
        writable = False
    record("data_directory", writable, str(data_dir))

    connection = ConnectionConfig(settings.data_dir, settings.mode).public()
    wma_enabled = bool(connection.get("enabled"))
    wma_configured = bool(connection.get("configured"))
    sdk_available = importlib.util.find_spec("cloud_agent_sdk") is not None
    record("wma_configuration", (not wma_enabled) or (wma_configured and sdk_available), {
        "enabled": wma_enabled,
        "configured": wma_configured,
        "sdk_available": sdk_available,
        "agent_id": connection.get("agent_id", ""),
        "source_app": connection.get("source_app", ""),
    })
    # These are rollout choices, not blockers for a protected staging deployment.
    record("public_catalog", True, settings.public_catalog, required=False)
    record("self_registration", True, settings.allow_registration, required=False)

    failed = [item for item in checks if item["required"] and not item["ok"]]
    return {
        "release": RELEASE,
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_required": [item["name"] for item in failed],
        "wma_called": False,
        "data_modified": False,
    }
