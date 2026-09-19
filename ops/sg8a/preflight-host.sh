#!/usr/bin/env bash
set -euo pipefail
missing=0
for command in python3.13 nginx systemctl pg_dump pg_restore psql curl sha256sum tar; do
  if command -v "$command" >/dev/null 2>&1; then printf 'OK   %s\n' "$command"; else printf 'MISS %s\n' "$command"; missing=1; fi
done
python3.13 - <<'PY'
import sys
print('PYTHON='+sys.version.split()[0])
assert sys.version_info[:2]==(3,13), 'SG8-A host expects Python 3.13'
PY
for env in staging production; do
  file="/etc/deepaha/${env}.env"
  if [[ -r "$file" ]]; then echo "OK   $file"; else echo "MISS $file"; fi
done
if ((missing)); then echo 'HOST_PREFLIGHT=FAIL'; exit 1; fi
echo 'HOST_PREFLIGHT=PASS (DNS/TLS/PostgreSQL credentials are checked during deployment, not here)'
