#!/usr/bin/env bash
# Runs the application inside a GitHub Codespace (or any Linux machine without Docker).
#
#   bash scripts/codespace.sh setup    install into .venv (once, a few minutes)
#   bash scripts/codespace.sh start    start the server in the background, if it is not running
#   bash scripts/codespace.sh stop     stop it
#   bash scripts/codespace.sh update   fetch the newest version from GitHub and restart
#   bash scripts/codespace.sh info     print the address and the administrator login
#   bash scripts/codespace.sh logs     follow the server log
#
# State lives in .codespace/ (git-ignored): the database and uploads, the log, and the
# administrator password generated on first start. Set DFD_ADMIN_USERNAME and
# DFD_ADMIN_PASSWORD (for example as Codespaces secrets) to choose the login yourself.
# With DFD_PUBLIC_PORT=true (the dev container default) the address works without a GitHub login.
# With DFD_AUTO_UPDATE=true (also the default there) every start first fetches the newest version,
# so stopping and starting the codespace is enough to deploy what was pushed.
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

publish() {
  # Codespaces makes every forwarded port private again at each start, so this runs every time.
  [[ -n "${CODESPACE_NAME:-}" && "${DFD_PUBLIC_PORT:-false}" == "true" ]] || return 0
  if ! command -v gh >/dev/null 2>&1; then
    echo "gh is not installed: the address stays private" >&2
    return 0
  fi
  for _ in $(seq 10); do
    if gh codespace ports visibility "$PORT:public" --codespace "$CODESPACE_NAME" \
      >>"$STATE/publish.log" 2>&1; then
      touch "$STATE/public"
      return 0
    fi
    sleep 3
  done
  rm -f "$STATE/public"
  echo "Could not make port $PORT public; see $STATE/publish.log" >&2
}

setup() {
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  # CPU-only PyTorch first: the default wheel bundles CUDA and is several times larger.
  .venv/bin/pip install --quiet --extra-index-url "$TORCH_INDEX" --constraint constraints.txt \
    torch torchvision
  .venv/bin/pip install --quiet --extra-index-url "$TORCH_INDEX" --constraint constraints.txt \
    --editable .
  .venv/bin/dfd models --download
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
  if [[ -n "${CODESPACE_NAME:-}" ]]; then
    if [[ -f "$STATE/public" ]]; then
      echo "                     hemmelere açyk / open to anyone with the link"
    else
      echo "                     diňe size açyk / private to you"
    fi
  fi
  if [[ -f "$ADMIN_FILE" ]]; then
    echo "  Administrator:     $(sed -n 's/^DFD_ADMIN_USERNAME=//p' "$ADMIN_FILE")" \
      "/ $(sed -n 's/^DFD_ADMIN_PASSWORD=//p' "$ADMIN_FILE")"
  elif [[ -n "${DFD_ADMIN_USERNAME:-}" ]]; then
    echo "  Administrator:     $DFD_ADMIN_USERNAME (parol / password: DFD_ADMIN_PASSWORD)"
  fi
  echo "  Log:               bash scripts/codespace.sh logs"
  echo
}

# Fast-forwards the checkout. Never fatal: without network, or with local edits in the way, the
# version already on disk keeps running.
pull() {
  local before after
  before="$(git rev-parse HEAD)"
  if ! git pull --quiet --ff-only 2>/dev/null; then
    echo "update skipped: could not fast-forward (no network, or local changes)" >&2
    return 0
  fi
  after="$(git rev-parse HEAD)"
  if [[ "$before" == "$after" ]]; then
    echo "already up to date ($(git log -1 --format=%h))"
    return 0
  fi
  # The install is editable, so only a change of dependencies needs pip again.
  if [[ -x .venv/bin/pip ]] &&
    git diff --name-only "$before" "$after" | grep -qE '^(pyproject\.toml|constraints\.txt)$'; then
    .venv/bin/pip install --quiet --extra-index-url "$TORCH_INDEX" --constraint constraints.txt \
      --editable .
  fi
  .venv/bin/dfd models --download
  echo "updated to $(git log -1 --format='%h %s')"
}

start() {
  mkdir -p "$STATE"
  if healthy; then
    publish
    info
    return
  fi
  [[ "${DFD_AUTO_UPDATE:-false}" == "true" ]] && pull
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
  publish
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

# The dispatch is a function called from the last line, so bash has read the whole file before
# `pull` can replace it on disk.
main() {
  case "${1:-start}" in
    setup) setup ;;
    start) start ;;
    stop) stop ;;
    restart) stop && start ;;
    pull) pull ;;
    update) pull && stop && start ;;
    info) info ;;
    logs) tail -n 100 -f "$LOG" ;;
    *)
      echo "usage: $0 {setup|start|stop|restart|update|info|logs}" >&2
      exit 2
      ;;
  esac
}

main "$@"; exit $?
