#!/usr/bin/env bash
# Start / stop the local DesignForge stack in the background.
#   scripts/dev.sh start   → API :8000, worker, web :3000 (+ fake SketchUp bridge when GEOMETRY_ENGINE=sketchup_mcp)
#   scripts/dev.sh stop
#   scripts/dev.sh status
# Logs: var/log/<service>.log   PIDs: var/run/<service>.pid
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOG=$ROOT/var/log RUN=$ROOT/var/run
mkdir -p "$LOG" "$RUN"

# Load .env for this script (services read it too, via pydantic-settings / Next.js)
if [ -f .env ]; then set -a; . ./.env; set +a; fi

start_one() {  # name, command...
  local name=$1; shift
  if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
    echo "  $name already running (pid $(cat "$RUN/$name.pid"))"; return
  fi
  nohup "$@" > "$LOG/$name.log" 2>&1 &
  echo $! > "$RUN/$name.pid"
  echo "  $name started (pid $!, log var/log/$name.log)"
}

stop_one() {
  local name=$1 pidfile=$RUN/$1.pid
  [ -f "$pidfile" ] || return 0
  local pid; pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    pkill -TERM -P "$pid" 2>/dev/null || true   # children (npm → next, uvicorn reloader)
    kill -TERM "$pid" 2>/dev/null || true
    echo "  $name stopped"
  fi
  rm -f "$pidfile"
}

case "${1:-}" in
  start)
    echo "Starting DesignForge (AI_PROVIDER=${AI_PROVIDER:-mock}, GEOMETRY_ENGINE=${GEOMETRY_ENGINE:-gltf})"
    .venv/bin/df-migrate > "$LOG/migrate.log" 2>&1 || { echo "  migration failed: see var/log/migrate.log"; exit 1; }
    if [ "${GEOMETRY_ENGINE:-gltf}" = "sketchup_mcp" ] && ! nc -z 127.0.0.1 "${DF_BRIDGE_PORT:-9877}" 2>/dev/null; then
      # Nothing listening on the bridge port (SketchUp closed): use the stand-in so the MCP path still runs.
      start_one bridge .venv/bin/python extensions/sketchup-bridge/dev/fake_bridge.py
    fi
    start_one api .venv/bin/uvicorn df_api.main:app --port 8000
    start_one worker .venv/bin/df-worker
    start_one web npm --prefix apps/web run dev
    for _ in $(seq 1 60); do
      curl -sf localhost:8000/health >/dev/null 2>&1 && curl -sf -o /dev/null localhost:3000 2>&1 && break; sleep 1
    done
    curl -sf localhost:8000/health >/dev/null 2>&1 && echo "Ready: http://localhost:3000" || echo "Not ready yet: check var/log/*.log"
    ;;
  stop)
    for s in web worker api bridge; do stop_one "$s"; done ;;
  status)
    for s in api worker web bridge; do
      if [ -f "$RUN/$s.pid" ] && kill -0 "$(cat "$RUN/$s.pid")" 2>/dev/null; then echo "  $s: running"; else echo "  $s: stopped"; fi
    done ;;
  *) echo "usage: $0 start|stop|status"; exit 2 ;;
esac
