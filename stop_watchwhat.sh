#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/watchwhat.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No PID file found. WatchWhat may not be running."
  exit 0
fi

PID="$(cat "$PID_FILE")"
if [[ -z "$PID" ]]; then
  echo "PID file is empty; removing it."
  rm -f "$PID_FILE"
  exit 0
fi

if ! kill -0 "$PID" 2>/dev/null; then
  echo "Process $PID is not running; cleaning stale PID file."
  rm -f "$PID_FILE"
  exit 0
fi

kill "$PID"

for _ in {1..10}; do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "WatchWhat stopped."
    exit 0
  fi
  sleep 1
done

kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "WatchWhat force-stopped."
