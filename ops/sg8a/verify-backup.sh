#!/usr/bin/env bash
set -euo pipefail
DIR="${1:-}"
[[ -d "$DIR" ]] || { echo '用法: verify-backup.sh /var/backups/deepaha/.../TIMESTAMP' >&2; exit 2; }
(cd "$DIR" && sha256sum -c SHA256SUMS && pg_restore --list database.dump >/dev/null && tar -tzf objects.tar.gz >/dev/null && python3.13 -m json.tool BACKUP_METADATA.json >/dev/null)
echo 'BACKUP_VERIFY=PASS'
