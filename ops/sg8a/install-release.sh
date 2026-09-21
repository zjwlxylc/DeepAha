#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo '请用root/sudo执行 install-release.sh' >&2; exit 2; fi
if (($# < 2)); then echo '用法: install-release.sh production|staging SOURCE_DIR [--sqlite-backup FILE]' >&2; exit 2; fi
ENVIRONMENT="$1"; SOURCE="$2"; shift 2
[[ "$ENVIRONMENT" == production || "$ENVIRONMENT" == staging ]] || { echo '环境只能是production或staging' >&2; exit 2; }
[[ -d "$SOURCE" ]] || { echo 'SOURCE_DIR不存在' >&2; exit 2; }
SQLITE_BACKUP=''
while (($#)); do
  case "$1" in
    --sqlite-backup) (($# >= 2)) || { echo '--sqlite-backup缺少文件' >&2; exit 2; }; SQLITE_BACKUP="$2"; shift 2;;
    *) echo "未知参数: $1" >&2; exit 2;;
  esac
done
SOURCE="$(cd "$SOURCE" && pwd)"
# R3 has a distinct schema and release identity. Do not silently reuse the old
# 3.8.0-rc1 directory or restart a pre-R3 worker on new membership tasks.
if [[ -f "$SOURCE/RELEASE_STATUS.json" ]] && grep -q 'mobile-r3' "$SOURCE/RELEASE_STATUS.json"; then
  echo 'R3禁止使用SG8-A历史自动安装器。先阅读 docs/services-r3/DEPLOYMENT.md，停服务、备份、upgrade-services及核验后再切换发布指针。' >&2
  exit 4
fi
VERSION="$(python3.13 - "$SOURCE/RELEASE_STATUS.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['release'])
PY
)"
[[ "$VERSION" == '3.8.0-rc1' ]] || { echo "不是SG8-A交付包: $VERSION" >&2; exit 3; }
ROOT="$SOURCE"
ENV_FILE="/etc/deepaha/${ENVIRONMENT}.env"
[[ -r "$ENV_FILE" ]] || { echo "缺少 $ENV_FILE" >&2; exit 3; }
TARGET="/opt/deepaha/releases/$VERSION"
CURRENT="/opt/deepaha/${ENVIRONMENT}-current"; PREVIOUS="/opt/deepaha/${ENVIRONMENT}-previous"
if [[ ! -d "$TARGET" ]]; then
  STAGE="/opt/deepaha/releases/.${VERSION}.$$"; rm -rf "$STAGE"; mkdir -p "$STAGE"
  cp -a "$SOURCE/." "$STAGE/"
  find "$STAGE" -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} + || true
  find "$STAGE" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
  mv "$STAGE" "$TARGET"
fi
if [[ ! -x "$TARGET/.venv-product/bin/python" ]]; then
  python3.13 -m venv "$TARGET/.venv-product"
  "$TARGET/.venv-product/bin/python" -m pip install --disable-pip-version-check -r "$TARGET/backend/requirements-postgres.txt"
fi
PYTHON="$TARGET/.venv-product/bin/python"
PYTHONPATH="$TARGET/backend/src" "$PYTHON" -m compileall -q "$TARGET/backend/src"

if [[ -n "$SQLITE_BACKUP" ]]; then
  [[ -r "$SQLITE_BACKUP" ]] || { echo 'SQLite备份不可读' >&2; exit 3; }
  PYTHONPATH="$TARGET/backend/src" python3.13 "$TARGET/ops/sg8a/envtool.py" run "$ENV_FILE" "$PYTHON" -m deepaha.product.cli migrate-sqlite-backup "$SQLITE_BACKUP" --report "/var/lib/deepaha/${ENVIRONMENT}/migration-${VERSION}.json"
fi
# Read-only gate before any symlink/service switch.
PYTHONPATH="$TARGET/backend/src" python3.13 "$TARGET/ops/sg8a/envtool.py" run "$ENV_FILE" "$PYTHON" -m deepaha.product.cli deploy-check

OLD=''
if [[ -L "$CURRENT" ]]; then
  OLD="$(readlink -f "$CURRENT")"
  "$TARGET/ops/sg8a/backup-postgres.sh" "$ENVIRONMENT" --leave-stopped >/dev/null
fi
DEPLOY_COMPLETE=0
recover_on_exit() {
  code=$?
  if (( code != 0 )) && (( DEPLOY_COMPLETE == 0 )); then
    systemctl stop "deepaha-worker@${ENVIRONMENT}.service" "deepaha-api@${ENVIRONMENT}.service" 2>/dev/null || true
    if [[ -n "$OLD" ]]; then
      echo '发布中断，恢复旧代码指针并重新启动旧服务。数据库不会自动回滚。' >&2
      ln -sfn "$OLD" "$CURRENT" || true
      systemctl restart "deepaha-api@${ENVIRONMENT}.service" "deepaha-worker@${ENVIRONMENT}.service" || true
    else
      echo '首次发布中断：已停止新服务并移除current指针。数据库/原件不自动删除。' >&2
      rm -f "$CURRENT" || true
    fi
  fi
  exit $code
}
trap recover_on_exit EXIT
if [[ -n "$OLD" ]]; then ln -sfn "$OLD" "$PREVIOUS"; fi
ln -sfn "$TARGET" "$CURRENT"
systemctl enable "deepaha-api@${ENVIRONMENT}.service" "deepaha-worker@${ENVIRONMENT}.service" >/dev/null
systemctl restart "deepaha-api@${ENVIRONMENT}.service" "deepaha-worker@${ENVIRONMENT}.service"
"$TARGET/ops/sg8a/smoke.sh" "$ENVIRONMENT"
DEPLOY_COMPLETE=1
trap - EXIT
echo "DEPLOY=PASS environment=$ENVIRONMENT release=$VERSION"
