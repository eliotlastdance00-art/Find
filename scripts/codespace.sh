#!/usr/bin/env bash
# Runs the application inside a GitHub Codespace (or any Linux machine without Docker).
#
#   bash scripts/codespace.sh setup    install into .venv (once, a few minutes)
#   bash scripts/codespace.sh start    start the server in the background, if it is not running
#   bash scripts/codespace.sh stop     stop it
#   bash scripts/codespace.sh info     print the address and the administrator login
#   bash scripts/codespace.sh logs     follow the server log
#
# State lives in .codespace/ (git-ignored): the database and uploads, the log, and the
# administrator password generated on first start. Set DFD_ADMIN_USERNAME and
# DFD_ADMIN_PASSWORD (for example as Codespaces secrets) to choose the login yourself.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STATE="${DFD_STATE_DIR:-$ROOT/.codespace}"
PORT="${DFD_PORT:-8000}"
LOG="$STATE/server.log"
PID_FILE="$STATE/server.pid"
ADMIN_FILE="$STATE/admin.env"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cpu}"

healthy() {
  curl --fail --silent --max-time 3 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1
}

address() {
  if [[ -n "${CODESPACE_NAME:-}" ]]; then
    echo "https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  else
    echo "http://localhost:$PORT"
  fi
}

setup() {
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  # CPU-only PyTorch first: the default wheel bundles CUDA and is several times larger.
  .venv/bin/pip install --quiet --extra-index-url "$TORCH_INDEX" --constraint constraints.txt \
    torch torchvision
  .venv/bin/pip install --quiet --extra-index-url "$TORCH_INDEX" --constraint constraints.txt \
    --editable .
  .venv/bin/dfd models
}

credentials() {
  mkdir -p "$STATE"
  if [[ -n "${DFD_ADMIN_USERNAME:-}" && -n "${DFD_ADMIN_PASSWORD:-}" ]]; then
    return
  fi
  if [[ ! -f "$ADMIN_FILE" ]]; then
    # Without a configured administrator the first visitor to register would become one.
    (
      umask 077
      printf 'DFD_ADMIN_USERNAME=admin\nDFD_ADMIN_PASSWORD=%s\n' \
        "$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')" >"$ADMIN_FILE"
    )
  fi
  set -a
  # shellcheck disable=SC1090
  source "$ADMIN_FILE"
  set +a
}

info() {
  local state="işlänok / not running"
  healthy && state="işleýär / running"
  echo
  echo "  Deepfake Detektor: $state"
  echo "  Salgy / address:   $(address)"
  if [[ -f "$ADMIN_FILE" ]]; then
    echo "  Administrator:     $(sed -n 's/^DFD_ADMIN_USERNAME=//p' "$ADMIN_FILE")" \
      "/ $(sed -n 's/^DFD_ADMIN_PASSWORD=//p' "$ADMIN_FILE")"
  elif [[ -n "${DFD_ADMIN_USERNAME:-}" ]]; then
    echo "  Administrator:     $DFD_ADMIN_USERNAME (parol / password: DFD_ADMIN_PASSWORD)"
  fi
  echo "  Log:               bash scripts/codespace.sh logs"
  echo
}

start() {
  if healthy; then
    info
    return
  fi
  [[ -x .venv/bin/dfd ]] || setup
  credentials
  mkdir -p "$STATE/data"
  # setsid + nohup: the server must outlive the lifecycle command that starts it.
  DFD_DATA_DIR="${DFD_DATA_DIR:-$STATE/data}" DFD_WEIGHTS_DIR="${DFD_WEIGHTS_DIR:-$ROOT/weights}" \
    setsid nohup .venv/bin/dfd serve --host 0.0.0.0 --port "$PORT" --forwarded-allow-ips "*" \
    >>"$LOG" 2>&1 </dev/null &
  echo $! >"$PID_FILE"
  for _ in $(seq 90); do
    healthy && break
    kill -0 "$(cat "$PID_FILE")" 2>/dev/null || break
    sleep 1
  done
  if ! healthy; then
    echo "The server did not start; last log lines:" >&2
    tail -n 40 "$LOG" >&2 || true
    exit 1
  fi
  info
}

stop() {
  if [[ -f "$PID_FILE" ]] && kill "$(cat "$PID_FILE")" 2>/dev/null; then
    for _ in $(seq 20); do
      kill -0 "$(cat "$PID_FILE")" 2>/dev/null || break
      sleep 1
    done
    echo "stopped"
  else
    echo "not running"
  fi
  rm -f "$PID_FILE"
}

case "${1:-start}" in
  setup) setup ;;
  start) start ;;
  stop) stop ;;
  restart) stop && start ;;
  info) info ;;
  logs) tail -n 100 -f "$LOG" ;;
  *)
    echo "usage: $0 {setup|start|stop|restart|info|logs}" >&2
    exit 2
    ;;
esac
