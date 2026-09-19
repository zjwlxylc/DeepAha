#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo '请用root/sudo执行 rollback.sh' >&2; exit 2; fi
ENVIRONMENT="${1:-}"; [[ "$ENVIRONMENT" == production || "$ENVIRONMENT" == staging ]] || { echo '用法: rollback.sh production|staging' >&2; exit 2; }
CURRENT="/opt/deepaha/${ENVIRONMENT}-current"; PREVIOUS="/opt/deepaha/${ENVIRONMENT}-previous"
[[ -L "$CURRENT" && -L "$PREVIOUS" ]] || { echo '没有可回退的两个发布指针' >&2; exit 3; }
CUR="$(readlink -f "$CURRENT")"; PREV="$(readlink -f "$PREVIOUS")"
CUR_GEN="$(python3.13 -c 'import json,sys;print(json.load(open(sys.argv[1]))["database_generation"])' "$CUR/RELEASE_COMPATIBILITY.json")"
PREV_GEN="$(python3.13 -c 'import json,sys;print(json.load(open(sys.argv[1]))["database_generation"])' "$PREV/RELEASE_COMPATIBILITY.json")"
[[ "$CUR_GEN" == "$PREV_GEN" ]] || { echo '数据库代际不同，禁止自动代码回退；需按恢复手册人工处理。' >&2; exit 4; }
if [[ "$ENVIRONMENT" == production ]]; then "$CUR/ops/sg8a/backup-postgres.sh" production >/dev/null; fi
ln -sfn "$PREV" "$CURRENT"; ln -sfn "$CUR" "$PREVIOUS"
systemctl restart "deepaha-api@${ENVIRONMENT}.service" "deepaha-worker@${ENVIRONMENT}.service"
if ! "$PREV/ops/sg8a/smoke.sh" "$ENVIRONMENT"; then
  ln -sfn "$CUR" "$CURRENT"; ln -sfn "$PREV" "$PREVIOUS"
  systemctl restart "deepaha-api@${ENVIRONMENT}.service" "deepaha-worker@${ENVIRONMENT}.service"
  echo '回退版本Smoke失败，已恢复原代码指针。' >&2; exit 5
fi
echo "ROLLBACK=PASS environment=$ENVIRONMENT release=$(basename "$PREV")"
