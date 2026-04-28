#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  CLOZEHIVE MCP Servers — start all services
#
#  Usage:
#    chmod +x start_all.sh
#    ./start_all.sh          # start everything
#    ./start_all.sh stop     # kill all MCP processes
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PID_DIR="$SCRIPT_DIR/.pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Stop mode ─────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "stop" ]]; then
    info "Stopping all MCP servers …"
    for pid_file in "$PID_DIR"/*.pid; do
        [[ -f "$pid_file" ]] || continue
        pid=$(cat "$pid_file")
        name=$(basename "$pid_file" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" && info "Stopped $name (PID $pid)"
        else
            warn "$name (PID $pid) was not running"
        fi
        rm -f "$pid_file"
    done
    info "All servers stopped."
    exit 0
fi

# ── Dependency check ──────────────────────────────────────────────────────────
if ! python3 -c "import fastmcp" 2>/dev/null; then
    warn "fastmcp not installed — installing from requirements-base.txt …"
    pip install -r "$SCRIPT_DIR/requirements-base.txt" -q
fi

# ── Start MCP servers ─────────────────────────────────────────────────────────
start_server() {
    local name=$1
    local dir=$2
    local log="$LOG_DIR/${name}.log"
    local pid_file="$PID_DIR/${name}.pid"

    info "Starting $name server …"
    pushd "$dir" > /dev/null
    python3 server.py > "$log" 2>&1 &
    echo $! > "$pid_file"
    popd > /dev/null
    info "$name started (PID $(cat "$pid_file")) — logs: $log"
}

start_server "weather" "$SCRIPT_DIR/weather"
sleep 1

start_server "vision"  "$SCRIPT_DIR/vision"
sleep 1

start_server "outfit"  "$SCRIPT_DIR/outfit"
sleep 1

start_server "packing" "$SCRIPT_DIR/packing"
sleep 2   # give MCP servers time to boot before gateway connects

# ── Start Gateway ─────────────────────────────────────────────────────────────
info "Starting AI Gateway …"
pushd "$SCRIPT_DIR/agent" > /dev/null
python3 gateway.py > "$LOG_DIR/gateway.log" 2>&1 &
echo $! > "$PID_DIR/gateway.pid"
popd > /dev/null
info "Gateway started (PID $(cat "$PID_DIR/gateway.pid")) — logs: $LOG_DIR/gateway.log"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  CLOZEHIVE MCP Stack is running               ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo "  🌤  Weather   →  http://localhost:8004/sse"
echo "  👁  Vision    →  http://localhost:8001/sse"
echo "  👗  Outfit    →  http://localhost:8002/sse"
echo "  🧳  Packing   →  http://localhost:8003/sse"
echo "  🚀  Gateway   →  http://localhost:8005"
echo "  📖  API docs  →  http://localhost:8005/docs"
echo ""
echo "  Stop all:  ./start_all.sh stop"
echo ""
