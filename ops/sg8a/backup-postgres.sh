#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo '请用root/sudo执行 backup-postgres.sh' >&2; exit 2; fi
ENVIRONMENT="${1:-}"; MODE="${2:-}"
[[ "$ENVIRONMENT" == production || "$ENVIRONMENT" == staging ]] || { echo '用法: backup-postgres.sh production|staging [--leave-stopped]' >&2; exit 2; }
[[ -z "$MODE" || "$MODE" == '--leave-stopped' ]] || { echo '未知参数' >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="/etc/deepaha/${ENVIRONMENT}.env"
[[ -r "$ENV_FILE" ]] || { echo "缺少 $ENV_FILE" >&2; exit 3; }
DATA_DIR="$(python3.13 "$ROOT/ops/sg8a/envtool.py" get "$ENV_FILE" DEEPAHA_DATA_DIR)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="/var/backups/deepaha/${ENVIRONMENT}/${STAMP}"
umask 077
mkdir -p "$DEST"
API="deepaha-api@${ENVIRONMENT}.service"; WORKER="deepaha-worker@${ENVIRONMENT}.service"
API_WAS_ACTIVE=0; WORKER_WAS_ACTIVE=0
systemctl is-active --quiet "$API" && API_WAS_ACTIVE=1 || true
systemctl is-active --quiet "$WORKER" && WORKER_WAS_ACTIVE=1 || true
restart_services() {
  if [[ "$MODE" != '--leave-stopped' ]]; then
    ((API_WAS_ACTIVE)) && systemctl start "$API" || true
    ((WORKER_WAS_ACTIVE)) && systemctl start "$WORKER" || true
  fi
}
trap restart_services EXIT
((WORKER_WAS_ACTIVE)) && systemctl stop "$WORKER"
((API_WAS_ACTIVE)) && systemctl stop "$API"
python3.13 "$ROOT/ops/sg8a/envtool.py" run "$ENV_FILE" pg_dump --format=custom --file="$DEST/database.dump"
if [[ -d "$DATA_DIR/objects" ]]; then
  tar --exclude='objects/deepaha-raw/.locks' -C "$DATA_DIR" -czf "$DEST/objects.tar.gz" objects
else
  tar -czf "$DEST/objects.tar.gz" --files-from /dev/null
fi
CURRENT="/opt/deepaha/${ENVIRONMENT}-current"; RELEASE='UNKNOWN'
[[ -L "$CURRENT" ]] && RELEASE="$(basename "$(readlink -f "$CURRENT")")"
python3.13 - "$DEST/BACKUP_METADATA.json" "$ENVIRONMENT" "$STAMP" "$RELEASE" <<'PY'
import json,sys
json.dump({'format':1,'environment':sys.argv[2],'created_at_utc':sys.argv[3],'release':sys.argv[4],
           'credentials_included':False,'services_quiesced':True},open(sys.argv[1],'w',encoding='utf-8'),indent=2)
PY
(
  cd "$DEST"
  sha256sum database.dump objects.tar.gz BACKUP_METADATA.json > SHA256SUMS
  pg_restore --list database.dump >/dev/null
  tar -tzf objects.tar.gz >/dev/null
)
chmod 600 "$DEST"/*
echo "$DEST"
