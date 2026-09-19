#!/usr/bin/env bash
set -euo pipefail
ENVIRONMENT="${1:-}"
[[ "$ENVIRONMENT" == production || "$ENVIRONMENT" == staging ]] || { echo '用法: smoke.sh production|staging' >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="/etc/deepaha/${ENVIRONMENT}.env"
PORT="$(python3.13 "$ROOT/ops/sg8a/envtool.py" get "$ENV_FILE" DEEPAHA_PORT)"
BASE="http://127.0.0.1:${PORT}"
LIVE="$(curl --fail --silent --show-error --max-time 8 "$BASE/health/live")"
READY="$(curl --fail --silent --show-error --max-time 8 "$BASE/health/ready")"
curl --fail --silent --show-error --max-time 8 "$BASE/" >/dev/null
python3.13 - "$LIVE" "$READY" <<'PY'
import json,sys
live=json.loads(sys.argv[1]);ready=json.loads(sys.argv[2])
assert live.get('live') is True and live.get('version')=='3.8.0-rc1',live
assert ready.get('database_read')=='ok',ready
print('HTTP_SMOKE=PASS version='+live['version'])
PY
