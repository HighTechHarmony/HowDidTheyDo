#!/usr/bin/env bash
set -euo pipefail

# Simple service manager for the howdidtheydo daemon and API.
# Usage: ./scripts/manage_services.sh start|stop|restart|status

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_CMD="${PYTHON_CMD:-$ROOT_DIR/.venv/bin/python}"
DATA_DIR="$ROOT_DIR/data"
LOG_DIR="$ROOT_DIR/logs"
API_PID_FILE="$DATA_DIR/api.pid"
DAEMON_PID_FILE="$DATA_DIR/daemon.pid"
API_LOG="$LOG_DIR/api.log"
DAEMON_LOG="$LOG_DIR/daemon.log"

ensure_dirs() {
  mkdir -p "$DATA_DIR" "$LOG_DIR"
}

is_running() {
  local pidfile="$1"
  if [ -f "$pidfile" ]; then
    local pid; pid=$(cat "$pidfile")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_api() {
  if is_running "$API_PID_FILE"; then
    echo "API already running (pid $(cat $API_PID_FILE))."
    return
  fi
  echo "Starting API..."
  nohup bash -c "cd '$ROOT_DIR' && \"$PYTHON_CMD\" -m backend.api" > "$API_LOG" 2>&1 &
  echo $! > "$API_PID_FILE"
  echo "API started, pid $(cat $API_PID_FILE). Logs: $API_LOG"
}

start_daemon() {
  if is_running "$DAEMON_PID_FILE"; then
    echo "Daemon already running (pid $(cat $DAEMON_PID_FILE))."
    return
  fi
  echo "Starting daemon..."
  nohup bash -c "cd '$ROOT_DIR' && \"$PYTHON_CMD\" -m backend.daemon" > "$DAEMON_LOG" 2>&1 &
  echo $! > "$DAEMON_PID_FILE"
  echo "Daemon started, pid $(cat $DAEMON_PID_FILE). Logs: $DAEMON_LOG"
}

stop_service() {
  local pidfile="$1"
  if [ ! -f "$pidfile" ]; then
    echo "No pidfile $pidfile, not running?"
    return
  fi
  local pid; pid=$(cat "$pidfile")
  if [ -z "$pid" ]; then
    echo "Pidfile empty, removing."; rm -f "$pidfile"; return
  fi
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping pid $pid..."
    kill "$pid"
    # give it a moment
    for i in 1 2 3 4 5; do
      if kill -0 "$pid" 2>/dev/null; then
        sleep 1
      else
        break
      fi
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "Pid $pid still running, sending SIGKILL..."
      kill -9 "$pid" || true
    fi
  else
    echo "Process $pid not running."
  fi
  rm -f "$pidfile" || true
}

status() {
  if is_running "$API_PID_FILE"; then
    echo "API running (pid $(cat $API_PID_FILE))"
  else
    echo "API stopped"
  fi
  if is_running "$DAEMON_PID_FILE"; then
    echo "Daemon running (pid $(cat $DAEMON_PID_FILE))"
  else
    echo "Daemon stopped"
  fi
}

case "${1:-}" in
  start)
    ensure_dirs
    start_api
    start_daemon
    ;;
  stop)
    stop_service "$DAEMON_PID_FILE"
    stop_service "$API_PID_FILE"
    ;;
  restart)
    $0 stop
    sleep 1
    $0 start
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 start|stop|restart|status"
    exit 2
    ;;
esac
