#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo '请用root/sudo执行 create-beta-user.sh' >&2; exit 2; fi
ENVIRONMENT="${1:-}"; USERNAME="${2:-}"
[[ "$ENVIRONMENT" == production || "$ENVIRONMENT" == staging ]] && [[ -n "$USERNAME" ]] || { echo '用法: create-beta-user.sh production|staging USERNAME' >&2; exit 2; }
CURRENT="/opt/deepaha/${ENVIRONMENT}-current"; ENV_FILE="/etc/deepaha/${ENVIRONMENT}.env"
[[ -L "$CURRENT" ]] || { echo '环境尚未部署' >&2; exit 3; }
PYTHON="$(readlink -f "$CURRENT")/.venv-product/bin/python"
PYTHONPATH="$(readlink -f "$CURRENT")/backend/src" python3.13 "$(readlink -f "$CURRENT")/ops/sg8a/envtool.py" run "$ENV_FILE" "$PYTHON" -m deepaha.product.cli user-add "$USERNAME" --roles user
