-- REFERENCE RESEARCH STAGING ONLY. NOT A MIGRATION FOR THE EXISTING DEEPAHA SCHEMA.
-- Apply only to an explicitly authorized isolated environment; initialize metadata via repository.initialize().

CREATE TABLE IF NOT EXISTS scout_import_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1), schema_version TEXT NOT NULL,
        target_id TEXT NOT NULL UNIQUE, generation INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS scout_import_batch (
        batch_id TEXT PRIMARY KEY, producer TEXT NOT NULL, run_key TEXT NOT NULL,
        package_hash TEXT NOT NULL, raw_hash TEXT NOT NULL, raw_handoff BLOB NOT NULL,
        actor TEXT NOT NULL, created_at TEXT NOT NULL, receipt_json TEXT NOT NULL,
        UNIQUE(producer, run_key));

CREATE TABLE IF NOT EXISTS scout_import_asset (
        asset_id TEXT PRIMARY KEY, producer TEXT NOT NULL, kind TEXT NOT NULL,
        asset_key TEXT NOT NULL, identity_hash TEXT, external_revision TEXT,
        system_revision INTEGER NOT NULL CHECK(system_revision > 0),
        content_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
        UNIQUE(producer, kind, asset_key), UNIQUE(producer, kind, identity_hash));

CREATE TABLE IF NOT EXISTS scout_import_alias (
        producer TEXT NOT NULL, kind TEXT NOT NULL, alias_key TEXT NOT NULL,
        asset_id TEXT NOT NULL REFERENCES scout_import_asset(asset_id),
        PRIMARY KEY(producer, kind, alias_key));

CREATE TABLE IF NOT EXISTS scout_import_revision (
        asset_id TEXT NOT NULL REFERENCES scout_import_asset(asset_id),
        system_revision INTEGER NOT NULL, batch_id TEXT NOT NULL REFERENCES scout_import_batch(batch_id),
        external_revision TEXT, content_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
        PRIMARY KEY(asset_id, system_revision));

CREATE TABLE IF NOT EXISTS scout_import_file (
        batch_id TEXT NOT NULL REFERENCES scout_import_batch(batch_id), name TEXT NOT NULL,
        sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, content BLOB NOT NULL,
        PRIMARY KEY(batch_id, name));

CREATE TABLE IF NOT EXISTS scout_import_link (
        batch_id TEXT NOT NULL REFERENCES scout_import_batch(batch_id),
        ref_kind TEXT NOT NULL, ref_key TEXT NOT NULL,
        asset_id TEXT NOT NULL REFERENCES scout_import_asset(asset_id),
        PRIMARY KEY(batch_id, ref_kind, ref_key));
