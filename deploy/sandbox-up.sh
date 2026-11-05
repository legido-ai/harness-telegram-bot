#!/usr/bin/env bash
# Start (or refresh) the sandbox test rig for the Telegram bot.
#
# Creates a throwaway agent workspace, a local server password, and brings up
# two containers: a sandbox OpenCode server and the bot pointed at it.
#
# Requirements: docker with compose, and a .env in the repo root with
# TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USER_IDS.
#
# Usage: deploy/sandbox-up.sh [--no-build]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX_DIR="${SANDBOX_DIR:-/tmp/opencode/otb-sandbox}"
PASSWORD_FILE="${PASSWORD_FILE:-/tmp/opencode/otb-password}"
COMPOSE_FILE="$REPO_ROOT/deploy/sandbox-compose.yml"

fail() { printf 'sandbox-up: %s\n' "$1" >&2; exit 1; }

command -v docker >/dev/null || fail "docker not found"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin not installed"

# Gate: the daemon must be able to start processes. A dead runtime accepts
# commands and fails later with ENOTCONN or ENOSYS; catching it here saves
# twenty minutes of confusion.
if ! docker run --rm alpine:3.22 true >/dev/null 2>&1; then
  fail "docker cannot start containers (runtime broken); fix the host first"
fi

[ -f "$REPO_ROOT/.env" ] || fail "missing $REPO_ROOT/.env (copy .env.example and fill it)"
grep -q '^TELEGRAM_BOT_TOKEN=..*' "$REPO_ROOT/.env" || fail "TELEGRAM_BOT_TOKEN is empty in .env"
grep -q '^TELEGRAM_ALLOWED_USER_IDS=..*' "$REPO_ROOT/.env" || fail "TELEGRAM_ALLOWED_USER_IDS is empty in .env"

[ -n "${OPENCODE_GO_API_KEY:-}" ] || fail "OPENCODE_GO_API_KEY is not set (the sandbox agent needs a provider)"

mkdir -p "$SANDBOX_DIR"

# The agent refuses to serve if the project config path cannot be read, and the
# mount source lives on the Docker host rather than here: seed it through a
# container so we always write to the same filesystem Docker sees.
docker run --rm -v "$SANDBOX_DIR:/workspace" alpine:3.22 sh -c '
  rm -rf /workspace/opencode.json
  printf "%s\n" "{\"\$schema\": \"https://opencode.ai/config.json\"}" > /workspace/opencode.json
  [ -f /workspace/README.md ] || printf "# Sandbox\n\nNothing here matters.\n" > /workspace/README.md
' >/dev/null

if [ ! -s "$PASSWORD_FILE" ]; then
  mkdir -p "$(dirname "$PASSWORD_FILE")"
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$PASSWORD_FILE"
  chmod 600 "$PASSWORD_FILE"
fi

export OPENCODE_PASSWORD="$(cat "$PASSWORD_FILE")"
export OPENCODE_GO_API_KEY
export SANDBOX_DIR
export SANDBOX_HEALTH_PORT="${SANDBOX_HEALTH_PORT:-8099}"

args=(compose -f "$COMPOSE_FILE" up -d)
[ "${1:-}" = "--no-build" ] || args+=(--build)

docker "${args[@]}"

printf 'waiting for the bot to report healthy'
for _ in $(seq 1 30); do
  health="$(docker exec otb-bot python -c \
    "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3).read().decode())" \
    2>/dev/null || true)"
  case "$health" in
    *'"status":"ok"'*)
      printf '\n%s\n' "$health"
      printf 'sandbox ready: agent on otb-agent:4199, health on 127.0.0.1:%s\n' "$SANDBOX_HEALTH_PORT"
      exit 0
      ;;
  esac
  printf '.'
  sleep 2
done

printf '\nlast health: %s\n' "${health:-unavailable}" >&2
docker logs --tail 20 otb-bot >&2 || true
exit 1
