#!/usr/bin/env bash
# Restore is intentionally empty-target only. It never cleans or overwrites an existing DB/store.
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo '请用root/sudo执行 restore-postgres-backup.sh' >&2; exit 2; fi
ENV_FILE="${1:-}"; BACKUP_DIR="${2:-}"
[[ -r "$ENV_FILE" && -d "$BACKUP_DIR" ]] || { echo '用法: restore-postgres-backup.sh TARGET_ENV_FILE BACKUP_DIR' >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
"$ROOT/ops/sg8a/verify-backup.sh" "$BACKUP_DIR" >/dev/null
DATA_DIR="$(python3.13 "$ROOT/ops/sg8a/envtool.py" get "$ENV_FILE" DEEPAHA_DATA_DIR)"
TABLES="$(python3.13 "$ROOT/ops/sg8a/envtool.py" run "$ENV_FILE" psql -Atqc "select count(*) from pg_tables where schemaname='public'")"
[[ "$TABLES" == '0' ]] || { echo '目标PostgreSQL不是空库，拒绝恢复' >&2; exit 4; }
if [[ -d "$DATA_DIR/objects" ]] && find "$DATA_DIR/objects" -type f -print -quit | grep -q .; then echo '目标原件目录不是空目录，拒绝恢复' >&2; exit 4; fi
install -d -m 0750 -o deepaha -g deepaha "$DATA_DIR"
python3.13 "$ROOT/ops/sg8a/envtool.py" run "$ENV_FILE" pg_restore --exit-on-error --no-owner --no-privileges --dbname="$(python3.13 "$ROOT/ops/sg8a/envtool.py" get "$ENV_FILE" PGDATABASE)" "$BACKUP_DIR/database.dump"
tar -C "$DATA_DIR" -xzf "$BACKUP_DIR/objects.tar.gz"
chown -R deepaha:deepaha "$DATA_DIR/objects" 2>/dev/null || true
# Restored sessions were valid at backup time; revoke them before any service starts.
python3.13 "$ROOT/ops/sg8a/envtool.py" run "$ENV_FILE" psql -v ON_ERROR_STOP=1 -qc "update product_sessions set revoked=true; delete from product_meta where key='worker_heartbeat';"
# R3 runtime intent survives the data restore, but must be explicitly re-enabled.
python3.13 "$ROOT/ops/sg8a/envtool.py" run "$ENV_FILE" psql -v ON_ERROR_STOP=1 -qc "update product_meta set value=((value::jsonb) || jsonb_build_object('enabled',false,'allow_site_enqueue',false,'lease_until',null,'next_due',null,'version',coalesce((value::jsonb->>'version')::int,0)+1,'last_result',jsonb_build_object('state','PAUSED_AFTER_RESTORE')))::text where key='services_runtime_v1';"
echo 'RESTORE_TO_EMPTY=PASS; service scheduling paused; WMA/WeChat credentials must be injected separately.' 
