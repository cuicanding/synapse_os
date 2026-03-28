#!/usr/bin/env bash
# SynapseOS 2.0 一键启动脚本
# 用法: ./run.sh start|stop|restart|logs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
DATA_DIR="$PROJECT_ROOT/data"

# PID 文件
BACKEND_PID_FILE="$PROJECT_ROOT/.synapse_backend.pid"
FRONTEND_PID_FILE="$PROJECT_ROOT/.synapse_frontend.pid"

# 日志文件
BACKEND_LOG="$PROJECT_ROOT/logs/synapse_backend.log"
FRONTEND_LOG="$PROJECT_ROOT/logs/synapse_frontend.log"

mkdir -p "$PROJECT_ROOT/logs"

# ─── Helpers ────────────────────────────────────────────────────────────────
is_linux() { [[ "$(uname)" == "Linux" ]]; }
is_macos() { [[ "$(uname)" == "Darwin" ]]; }

get_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid=$(cat "$pid_file" 2>/dev/null)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return 0
    fi
    rm -f "$pid_file"
  fi
  return 1
}

stop_pid() {
  local pid_file="$1"
  local name="$2"
  if pid=$(get_pid "$pid_file"); then
    echo "Stopping $name (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
    echo "$name stopped."
  else
    echo "$name is not running."
  fi
}

# ─── Check Dependencies ─────────────────────────────────────────────────────
check_deps() {
  local missing=()
  if ! command -v python3 &>/dev/null; then missing+=("python3"); fi
  if ! command -v pip3 &>/dev/null; then missing+=("pip3"); fi
  if ! command -v node &>/dev/null; then missing+=("node"); fi
  if ! command -v npm &>/dev/null; then missing+=("npm"); fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "❌ Missing dependencies: ${missing[*]}"
    echo "Please install them first."
    exit 1
  fi
}

# ─── Backend ────────────────────────────────────────────────────────────────
start_backend() {
  if pid=$(get_pid "$BACKEND_PID_FILE"); then
    echo "Backend already running (PID $pid). Skipping."
    return
  fi

  echo "Installing backend dependencies..."
  cd "$BACKEND_DIR"
  pip3 install -r requirements.txt -q

  echo "Starting backend (FastAPI + uvicorn)..."
  cd "$PROJECT_ROOT"
  PYTHONPATH="$PROJECT_ROOT/backend:$PROJECT_ROOT" \
    python3 -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning \
    > "$BACKEND_LOG" 2>&1 &

  local pid=$!
  echo "$pid" > "$BACKEND_PID_FILE"
  echo "Backend started (PID $pid)"
}

# ─── Frontend ───────────────────────────────────────────────────────────────
start_frontend() {
  if pid=$(get_pid "$FRONTEND_PID_FILE"); then
    echo "Frontend already running (PID $pid). Skipping."
    return
  fi

  echo "Installing frontend dependencies..."
  cd "$FRONTEND_DIR"
  if [[ ! -d "node_modules" ]]; then
    npm install
  fi

  echo "Starting frontend (Vite dev server)..."
  cd "$FRONTEND_DIR"
  npm run dev > "$FRONTEND_LOG" 2>&1 &

  local pid=$!
  echo "$pid" > "$FRONTEND_PID_FILE"
  echo "Frontend started (PID $pid)"
}

# ─── Main ────────────────────────────────────────────────────────────────────
case "${1:-}" in
  start)
    check_deps
    echo "🚀 Starting SynapseOS 2.0..."
    start_backend
    start_frontend
    sleep 2
    echo ""
    echo "✅ SynapseOS 2.0 is running!"
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    echo "   Frontend: http://localhost:5173"
    echo "   LAN:      http://${LOCAL_IP:-<your-ip>}:5173"
    echo "   Backend:  http://localhost:8000"
    echo "   API docs:  http://localhost:8000/docs"
    echo ""
    echo "📄 Logs:"
    echo "   Backend:  $BACKEND_LOG"
    echo "   Frontend: $FRONTEND_LOG"
    ;;

  stop)
    echo "🛑 Stopping SynapseOS 2.0..."
    stop_pid "$FRONTEND_PID_FILE" "Frontend"
    stop_pid "$BACKEND_PID_FILE" "Backend"
    echo "All stopped."
    ;;

  restart)
    echo "🔄 Restarting SynapseOS 2.0..."
    stop_pid "$FRONTEND_PID_FILE" "Frontend"
    stop_pid "$BACKEND_PID_FILE" "Backend"
    sleep 1
    check_deps
    start_backend
    start_frontend
    sleep 2
    echo ""
    echo "✅ SynapseOS 2.0 restarted!"
    echo "   Frontend: http://localhost:5173"
    echo "   Backend:  http://localhost:8000"
    ;;

  logs)
    echo "📋 SynapseOS 2.0 Logs"
    echo ""
    echo "─── Backend (last 30 lines) ───"
    tail -n 30 "$BACKEND_LOG" 2>/dev/null || echo "(no backend log)"
    echo ""
    echo "─── Frontend (last 30 lines) ───"
    tail -n 30 "$FRONTEND_LOG" 2>/dev/null || echo "(no frontend log)"
    ;;

  status)
    echo "SynapseOS 2.0 Status"
    echo ""
    if pid=$(get_pid "$BACKEND_PID_FILE"); then
      echo "✅ Backend:  running (PID $pid)"
    else
      echo "❌ Backend:  stopped"
    fi
    if pid=$(get_pid "$FRONTEND_PID_FILE"); then
      echo "✅ Frontend: running (PID $pid)"
    else
      echo "❌ Frontend: stopped"
    fi
    ;;

  *)
    echo "用法: $0 {start|stop|restart|logs|status}"
    exit 1
    ;;
esac
