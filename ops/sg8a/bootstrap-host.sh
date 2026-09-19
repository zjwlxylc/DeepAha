#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo '请用root/sudo执行 bootstrap-host.sh' >&2; exit 2; fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
missing=()
for command in python3.13 nginx systemctl pg_dump pg_restore curl sha256sum tar; do command -v "$command" >/dev/null 2>&1 || missing+=("$command"); done
if ((${#missing[@]})); then printf '服务器缺少命令：%s\n' "${missing[*]}" >&2; exit 3; fi
if ! id deepaha >/dev/null 2>&1; then useradd --system --create-home --home-dir /var/lib/deepaha --shell /usr/sbin/nologin deepaha; fi
install -d -m 0755 -o root -g root /opt/deepaha /opt/deepaha/releases
install -d -m 0750 -o deepaha -g deepaha /var/lib/deepaha/production /var/lib/deepaha/staging
install -d -m 0700 -o root -g root /var/backups/deepaha/production /var/backups/deepaha/staging
install -d -m 0750 -o root -g deepaha /etc/deepaha
install -m 0644 "$ROOT/infra/sg8a/systemd/deepaha-api@.service" /etc/systemd/system/deepaha-api@.service
install -m 0644 "$ROOT/infra/sg8a/systemd/deepaha-worker@.service" /etc/systemd/system/deepaha-worker@.service
systemctl daemon-reload
cat <<'EOF'
SG8-A host bootstrap 完成。
下一步：
1. 从 infra/sg8a/*.env.example 创建 /etc/deepaha/staging.env 与 production.env（chmod 640 root:deepaha）。
2. 单独创建 staging/prod PostgreSQL 数据库和最小权限账号。
3. staging.deepaha.com DNS/TLS 就绪后再合并 Nginx 示例；不要覆盖现有 www.deepaha.com 配置。
EOF
