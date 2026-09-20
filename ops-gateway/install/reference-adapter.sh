#!/bin/sh
set -eu

# REFERENCE ONLY.
# Codex must align service names and deployment directories to the real server.
# Unknown commands and parameters are rejected.

is_service() {
  [ "$1" = "api" ] ||
    [ "$1" = "web" ] ||
    [ "$1" = "worker" ] ||
    [ "$1" = "all" ]
}

is_log_service() {
  [ "$1" = "gateway" ] ||
    [ "$1" = "api" ] ||
    [ "$1" = "web" ] ||
    [ "$1" = "worker" ]
}

unit_for() {
  case "$1" in
    gateway) printf '%s\n' deepaha-ops-gateway.service ;;
    api) printf '%s\n' deepaha-api.service ;;
    web) printf '%s\n' deepaha-web.service ;;
    worker) printf '%s\n' deepaha-worker.service ;;
    *) return 2 ;;
  esac
}

case "${1:-}" in
  status)
    printf '{"gateway":"%s","api":"%s","web":"%s","worker":"%s"}\n'       "$(systemctl is-active deepaha-ops-gateway.service || true)"       "$(systemctl is-active deepaha-api.service || true)"       "$(systemctl is-active deepaha-web.service || true)"       "$(systemctl is-active deepaha-worker.service || true)"
    ;;
  logs)
    [ "$#" -eq 3 ] || exit 2
    is_log_service "$2" || exit 2
    case "$3" in
      *[!0-9]*|'') exit 2 ;;
    esac
    [ "$3" -ge 20 ] && [ "$3" -le 500 ] || exit 2
    journalctl       -u "$(unit_for "$2")"       -n "$3"       --no-pager       --output=short-iso
    ;;
  restart)
    [ "$#" -eq 2 ] || exit 2
    is_service "$2" || exit 2
    if [ "$2" = "all" ]; then
      systemctl restart         deepaha-api.service         deepaha-web.service         deepaha-worker.service
    else
      systemctl restart "$(unit_for "$2")"
    fi
    ;;
  deploy|backup|rollback|create-beta-user)
    echo "REFERENCE_ADAPTER_NOT_CONFIGURED_FOR_MUTATION" >&2
    echo "Codex must implement this action for the real server layout." >&2
    exit 78
    ;;
  *)
    echo "unsupported action" >&2
    exit 2
    ;;
esac
