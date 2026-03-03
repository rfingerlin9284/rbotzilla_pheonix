#!/usr/bin/env bash
# =============================================================================
# rbot_ctl.sh  —  RBOTzilla control script
# Usage: ./scripts/rbot_ctl.sh <command> [options]
#
# Commands:
#   start           Start OANDA engine (paper mode)
#   start-live      Start OANDA engine (live mode — requires --yes-live)
#   stop            Stop all RBOTzilla processes
#   restart         Stop then start
#   status          Show which processes are running
#   verify          Full system diagnostics (verify_system.py)
#   check-api       Quick OANDA API ping + account balance
#   check-positions Show open positions with PnL
#   logs            Tail the live OANDA engine log
#   logs-narration  Show last 30 narration events
#   mode-paper      Switch runtime config to PAPER mode
#   mode-live       Switch runtime config to LIVE mode (requires PIN)
#   police          Force-run position police (close sub-notional positions)
#   save            Git commit current state with timestamp
# =============================================================================

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PIDFILE="/tmp/rbotzilla_oanda.pid"
LOG="$ROOT/logs/oanda_headless.log"
PYTHON="$ROOT/venv/bin/python"
VENV_ACTIVATE="$ROOT/venv/bin/activate"

# ── colour helpers ──────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"
CYAN="\033[0;36m";  BOLD="\033[1m";      RESET="\033[0m"
ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠️  $*${RESET}"; }
err()  { echo -e "${RED}❌ $*${RESET}"; }
info() { echo -e "${CYAN}ℹ  $*${RESET}"; }
hdr()  { echo -e "\n${BOLD}━━━━  $*  ━━━━${RESET}"; }

# ── venv guard ───────────────────────────────────────────────────────────────
require_venv() {
    if [[ ! -f "$VENV_ACTIVATE" ]]; then
        err "venv not found at $ROOT/venv  — run: python3 -m venv venv && pip install -r requirements.txt"
        exit 1
    fi
    # shellcheck source=/dev/null
    source "$VENV_ACTIVATE"
}

# ── process helpers ──────────────────────────────────────────────────────────
is_running() {
    if [[ -f "$PIDFILE" ]]; then
        local pid
        pid=$(cat "$PIDFILE" 2>/dev/null || true)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"; return 0
        fi
    fi
    # fallback: check by process name
    pgrep -f "oanda_trading_engine.py" 2>/dev/null | head -1 || true
}

# ─────────────────────────────────────────────────────────────────────────────
CMD="${1:-help}"

case "$CMD" in

# ── start ────────────────────────────────────────────────────────────────────
start)
    hdr "START — OANDA engine (PAPER)"
    if pid=$(is_running); then
        warn "Already running (PID $pid). Use 'restart' to reload."
        exit 0
    fi
    require_venv
    mkdir -p "$ROOT/logs"
    nohup "$PYTHON" headless_runtime.py --broker oanda \
        >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 2
    if pid=$(is_running); then
        ok "Started — PID $pid  |  log: $LOG"
    else
        err "Process didn't stay up. Check $LOG"
        exit 1
    fi
    ;;

# ── start-live ───────────────────────────────────────────────────────────────
start-live)
    hdr "START — OANDA engine (LIVE ⚠️)"
    if pid=$(is_running); then
        warn "Already running (PID $pid). Use 'restart' to reload."
        exit 0
    fi
    require_venv
    # Live mode requires runtime config to be LIVE first
    "$PYTHON" -c "
from util.mode_manager import switch_mode
import os, sys
pin = int(os.environ.get('RICK_PIN', '0'))
if pin != 841921:
    print('❌  Set RICK_PIN=841921 in .env first')
    sys.exit(1)
switch_mode('LIVE', pin=841921, brokers=['oanda'])
print('✅  Mode set to LIVE')
"
    mkdir -p "$ROOT/logs"
    nohup "$PYTHON" headless_runtime.py --broker oanda \
        >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 2
    if pid=$(is_running); then
        ok "Started LIVE — PID $pid  |  log: $LOG"
    else
        err "Process didn't stay up. Check $LOG"
        exit 1
    fi
    ;;

# ── stop ─────────────────────────────────────────────────────────────────────
stop)
    hdr "STOP"
    killed=0
    # kill supervisor
    if [[ -f "$PIDFILE" ]]; then
        pid=$(cat "$PIDFILE" 2>/dev/null || true)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" && ok "Stopped supervisor PID $pid"
            killed=1
        fi
        rm -f "$PIDFILE"
    fi
    # kill any stray engine processes
    if pkill -f "oanda_trading_engine.py" 2>/dev/null; then
        ok "Killed oanda_trading_engine processes"
        killed=1
    fi
    if pkill -f "headless_runtime.py" 2>/dev/null; then
        ok "Killed headless_runtime processes"
        killed=1
    fi
    [[ $killed -eq 0 ]] && info "Nothing was running."
    ;;

# ── restart ──────────────────────────────────────────────────────────────────
restart)
    hdr "RESTART"
    "$0" stop
    sleep 2
    "$0" start
    ;;

# ── status ───────────────────────────────────────────────────────────────────
status)
    hdr "STATUS"
    echo ""
    supervisor_pids=$(pgrep -f "headless_runtime.py" 2>/dev/null || true)
    engine_pids=$(pgrep -f "oanda_trading_engine.py" 2>/dev/null || true)

    if [[ -n "$supervisor_pids" ]]; then
        ok "headless_runtime (supervisor):  PIDs $supervisor_pids"
    else
        warn "headless_runtime:  NOT running"
    fi

    if [[ -n "$engine_pids" ]]; then
        ok "oanda_trading_engine:           PIDs $engine_pids"
        # show uptime
        for pid in $engine_pids; do
            elapsed=$(ps -p "$pid" -o etime= 2>/dev/null | xargs || true)
            info "  └─ PID $pid  uptime: $elapsed"
        done
    else
        warn "oanda_trading_engine:           NOT running"
    fi

    echo ""
    info "Runtime mode:"
    require_venv
    "$PYTHON" -c "
from util.mode_manager import get_mode_info
m = get_mode_info()
print(f'  Mode    : {m[\"mode\"]}')
print(f'  OANDA   : {\"enabled\" if m[\"brokers\"].get(\"oanda\",{}).get(\"enabled\") else \"disabled\"}')
"
    ;;

# ── verify ───────────────────────────────────────────────────────────────────
verify)
    hdr "SYSTEM DIAGNOSTICS"
    require_venv
    "$PYTHON" verify_system.py
    ;;

# ── check-api ────────────────────────────────────────────────────────────────
check-api)
    hdr "OANDA API CHECK"
    require_venv
    "$PYTHON" - << 'PYEOF'
import os, sys
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()

import requests
token = os.environ.get('OANDA_PRACTICE_TOKEN') or os.environ.get('OANDA_TOKEN')
acct  = os.environ.get('OANDA_PRACTICE_ACCOUNT_ID') or os.environ.get('OANDA_ACCOUNT_ID')
base  = os.environ.get('OANDA_API_BASE', 'https://api-fxpractice.oanda.com')

if not token or not acct:
    print("❌  No credentials found in .env")
    sys.exit(1)

try:
    r = requests.get(f'{base}/v3/accounts/{acct}/summary',
                     headers={'Authorization': f'Bearer {token}'}, timeout=8)
    d = r.json()
    if 'account' in d:
        a = d['account']
        print(f'✅  OANDA API  ─  OK ({base})')
        print(f'   Account  : {a.get("id")}')
        print(f'   Currency : {a.get("currency")}')
        print(f'   Balance  : {a.get("balance")}')
        print(f'   NAV      : {a.get("NAV")}')
        print(f'   Margin%  : {a.get("marginUsed","?")} used / {a.get("marginAvailable","?")} avail')
        print(f'   Trades   : {a.get("openTradeCount")} open  |  Positions: {a.get("openPositionCount")}')
    else:
        print(f'❌  Unexpected response: {d}')
        sys.exit(1)
except Exception as e:
    print(f'❌  Connection failed: {e}')
    sys.exit(1)
PYEOF
    ;;

# ── check-positions ──────────────────────────────────────────────────────────
check-positions)
    hdr "OPEN POSITIONS"
    require_venv
    "$PYTHON" scripts/check_positions.py
    ;;

# ── logs ─────────────────────────────────────────────────────────────────────
logs)
    hdr "LIVE LOG  (Ctrl+C to exit)"
    mkdir -p "$ROOT/logs"
    touch "$LOG"
    tail -f "$LOG"
    ;;

# ── logs-narration ───────────────────────────────────────────────────────────
logs-narration)
    hdr "NARRATION LOG (last 30 events)"
    NFILE="$ROOT/narration.jsonl"
    if [[ ! -f "$NFILE" ]]; then
        warn "No narration.jsonl yet — engine hasn't run."
        exit 0
    fi
    require_venv
    "$PYTHON" - << 'PYEOF'
import json, os, sys
nfile = os.path.join(os.environ.get('ROOT', '.'), 'narration.jsonl')
if not os.path.exists(nfile):
    nfile = 'narration.jsonl'
try:
    lines = open(nfile).readlines()[-30:]
    for raw in lines:
        try:
            e = json.loads(raw)
            ts   = e.get('ts','')[:19]
            typ  = e.get('event_type','?')
            sym  = e.get('symbol','')
            det  = e.get('details',{})
            print(f"  {ts}  [{typ:20s}]  {sym:10s}  {det}")
        except Exception:
            print(raw.strip())
except Exception as ex:
    print(f'Error: {ex}'); sys.exit(1)
PYEOF
    ;;

# ── mode-paper ───────────────────────────────────────────────────────────────
mode-paper)
    hdr "SWITCH → PAPER MODE"
    require_venv
    "$PYTHON" -c "
from util.mode_manager import switch_mode, get_mode_info
switch_mode('PAPER', brokers=['oanda'])
m = get_mode_info()
print(f'✅  Mode is now: {m[\"mode\"]}')
"
    ;;

# ── mode-live ────────────────────────────────────────────────────────────────
mode-live)
    hdr "SWITCH → LIVE MODE  ⚠️  REAL MONEY"
    require_venv
    "$PYTHON" -c "
import os, sys
from util.mode_manager import switch_mode, get_mode_info
pin = int(os.environ.get('RICK_PIN', '0'))
if pin != 841921:
    print('❌  RICK_PIN not set or wrong. Export RICK_PIN=841921 first.')
    sys.exit(1)
switch_mode('LIVE', pin=841921, brokers=['oanda'])
m = get_mode_info()
print(f'✅  Mode is now: {m[\"mode\"]}')
"
    ;;

# ── police ───────────────────────────────────────────────────────────────────
police)
    hdr "POSITION POLICE  (close sub-\$15k positions)"
    require_venv
    "$PYTHON" -c "
import sys
sys.path.insert(0, '.')
from oanda_trading_engine import _rbz_force_min_notional_position_police
_rbz_force_min_notional_position_police()
print('✅  Position police sweep complete')
"
    ;;

# ── save ─────────────────────────────────────────────────────────────────────
save)
    hdr "GIT SAVE"
    cd "$ROOT"
    git add -A
    MSG="chore: manual save $(date '+%Y-%m-%d %H:%M')"
    if git diff --cached --quiet; then
        info "Nothing new to commit."
    else
        git commit -m "$MSG"
        ok "Committed: $MSG"
    fi
    ;;

# ── help ─────────────────────────────────────────────────────────────────────
help|--help|-h|*)
    echo ""
    echo -e "${BOLD}rbot_ctl.sh — RBOTzilla control script${RESET}"
    echo ""
    echo "  Process control:"
    echo "    start            Start OANDA engine (paper)"
    echo "    start-live       Start OANDA engine (live — set RICK_PIN first)"
    echo "    stop             Stop all RBOTzilla processes"
    echo "    restart          Stop + start"
    echo "    status           Show running processes + current mode"
    echo ""
    echo "  Diagnostics:"
    echo "    verify           Full system check (verify_system.py)"
    echo "    check-api        OANDA API ping + account balance"
    echo "    check-positions  Open trades + unrealised PnL"
    echo ""
    echo "  Logs:"
    echo "    logs             Tail live engine log (Ctrl+C to exit)"
    echo "    logs-narration   Last 30 narration events"
    echo ""
    echo "  Mode switching:"
    echo "    mode-paper       Switch to paper/practice mode"
    echo "    mode-live        Switch to live mode (RICK_PIN required)"
    echo ""
    echo "  Maintenance:"
    echo "    police           Force position police (close sub-\$15k)"
    echo "    save             git add -A && git commit with timestamp"
    echo ""
    ;;
esac
