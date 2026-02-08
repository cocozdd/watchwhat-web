#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/watchwhat.pid"
LOG_FILE="$RUN_DIR/watchwhat.log"

HOST="${WATCHWHAT_HOST:-127.0.0.1}"
PORT="${WATCHWHAT_PORT:-8000}"

mkdir -p "$RUN_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "WatchWhat is already running (PID $OLD_PID)."
    echo "URL: http://$HOST:$PORT"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

set -a
# shellcheck disable=SC1091
source "$ROOT_DIR/.env"
set +a

nohup "$ROOT_DIR/.venv/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
NEW_PID="$!"
echo "$NEW_PID" > "$PID_FILE"

sleep 1
if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "WatchWhat started."
  echo "PID: $NEW_PID"
  echo "URL: http://$HOST:$PORT"
  echo "Log: $LOG_FILE"
else
  echo "WatchWhat failed to start. Check log: $LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi
