#!/usr/bin/env bash
# =============================================================================
# rbot_ctl.sh  —  RBOTzilla control script
# Usage: ./scripts/rbot_ctl.sh <command> [options]
#
# Commands:
#   start           Start OANDA engine (paper mode)
#   start-live      Start OANDA engine (live mode — requires --yes-live)
#   start-auto      Start engine by current runtime mode (PAPER/LIVE)
#   stop            Stop all RBOTzilla processes
#   shutdown        Alias for stop
#   restart         Stop then start
#   refresh         Restart + manual diagnostics sweep
#   status          Show which processes are running
#   verify          Full system diagnostics (verify_system.py)
#   diagnostics     Manual systems + API health checks
#   check-api       Quick OANDA API ping + account balance
#   check-positions Show open positions with PnL
#   logs            Tail the live OANDA engine log
#   logs-narration  Show last 30 narration events
#   monitor         Persistent headless monitor (health + signals + PnL)
#   monitor-tmux    Persistent tmux dashboard monitor
#   edge-kpi        ET-day capital amplification KPI report
#   mode-paper      Switch runtime config to PAPER mode
#   mode-live       Switch runtime config to LIVE mode (requires PIN)
#   police          Force-run position police (close sub-notional positions)
#   save            Git commit current state with timestamp
# =============================================================================

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SELF="bash $ROOT/scripts/rbot_ctl.sh"

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
    pid="$(is_running || true)"
    if [[ -n "$pid" ]]; then
        warn "Already running (PID $pid). Use 'restart' to reload."
        exit 0
    fi
    require_venv
    mkdir -p "$ROOT/logs"
    rm -f /tmp/rbot_last_scan_key
    RBOT_MIN_SIGNAL_CONFIDENCE=0.75 RBOT_BE_TRIGGER_R=0.25 RBOT_SCALE_OUT_TRIGGER_R=0.75 RBOT_TRAIL_TRIGGER_R=1.00 RBOT_TRAIL_DISTANCE_R=0.20 RBOT_PROFIT_EXTRACTION_MODE=1 RBOT_GREEN_LOCK_PIPS=1.5 RBOT_MAX_LOSS_USD_PER_TRADE=30 RBOT_ALLOW_EXTENDED_DOLLAR_STOP=0 RBOT_MAX_PAIRS_PER_PLATFORM=6 RBOT_MAX_ACTIVE_POSITIONS=6 nohup "$PYTHON" headless_runtime.py --broker oanda \
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
    pid="$(is_running || true)"
    if [[ -n "$pid" ]]; then
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
    rm -f /tmp/rbot_last_scan_key
    RBOT_MIN_SIGNAL_CONFIDENCE=0.75 RBOT_BE_TRIGGER_R=0.25 RBOT_SCALE_OUT_TRIGGER_R=0.75 RBOT_TRAIL_TRIGGER_R=1.00 RBOT_TRAIL_DISTANCE_R=0.20 RBOT_PROFIT_EXTRACTION_MODE=1 RBOT_GREEN_LOCK_PIPS=1.5 RBOT_MAX_LOSS_USD_PER_TRADE=30 RBOT_ALLOW_EXTENDED_DOLLAR_STOP=0 RBOT_MAX_PAIRS_PER_PLATFORM=6 RBOT_MAX_ACTIVE_POSITIONS=6 nohup "$PYTHON" headless_runtime.py --broker oanda \
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

# ── start-auto ───────────────────────────────────────────────────────────────
start-auto)
    hdr "START — AUTONOMOUS ENGINE"
    require_venv
    MODE=$(
        "$PYTHON" - << 'PYEOF'
from util.mode_manager import get_mode_info
print((get_mode_info().get("mode") or "PAPER").upper())
PYEOF
    )
    info "Runtime mode detected: $MODE"
    if [[ "$MODE" == "LIVE" ]]; then
        bash "$ROOT/scripts/rbot_ctl.sh" start-live
    else
        bash "$ROOT/scripts/rbot_ctl.sh" start
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
            kill "$pid" 2>/dev/null || true
            ok "Stopped supervisor PID $pid"
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
    if [[ $killed -eq 0 ]]; then
        info "Nothing was running."
    fi
    ;;

# ── shutdown ─────────────────────────────────────────────────────────────────
shutdown)
    bash "$ROOT/scripts/rbot_ctl.sh" stop
    ;;

# ── restart ──────────────────────────────────────────────────────────────────
restart)
    hdr "RESTART"
    bash "$ROOT/scripts/rbot_ctl.sh" stop
    sleep 2
    bash "$ROOT/scripts/rbot_ctl.sh" start
    ;;

# ── refresh ──────────────────────────────────────────────────────────────────
refresh)
    hdr "RESTART + REFRESH"
    bash "$ROOT/scripts/rbot_ctl.sh" restart
    bash "$ROOT/scripts/rbot_ctl.sh" diagnostics
    ;;

# ── status ───────────────────────────────────────────────────────────────────
status)
    hdr "STATUS"
    supervisor_pids=$(pgrep -f "headless_runtime.py" 2>/dev/null || true)
    engine_pids=$(pgrep -f "oanda_trading_engine.py" 2>/dev/null || true)

    if [[ -n "$supervisor_pids" && -n "$engine_pids" ]]; then
        ok "Trading system is online and running."
        for pid in $engine_pids; do
            elapsed=$(ps -p "$pid" -o etime= 2>/dev/null | xargs || true)
            info "Engine uptime: $elapsed"
            break
        done
    elif [[ -n "$supervisor_pids" ]]; then
        warn "Supervisor is running, but trading engine is not active yet."
    elif [[ -n "$engine_pids" ]]; then
        warn "Trading engine is running without supervisor protection."
    else
        warn "Trading system is currently offline."
    fi

    info "Current runtime mode:"
    require_venv
    "$PYTHON" -c "
from util.mode_manager import get_mode_info
m = get_mode_info()
print(f'  - Mode: {m[\"mode\"]}')
print(f'  - OANDA trading: {\"enabled\" if m[\"brokers\"].get(\"oanda\",{}).get(\"enabled\") else \"disabled\"}')
"
    ;;

# ── diagnostics ──────────────────────────────────────────────────────────────
diagnostics)
    hdr "MANUAL DIAGNOSTICS"
    require_venv
    bash "$ROOT/scripts/rbot_ctl.sh" status
    echo ""
    bash "$ROOT/scripts/rbot_ctl.sh" check-api
    echo ""
    hdr "RUN DIAGNOSTICS (ENGINE + API + LOGS)"
    "$PYTHON" run_diagnostics.py --json || true
    if [[ -f /tmp/rbotzilla_diagnostics.json ]]; then
        ok "Diagnostics JSON: /tmp/rbotzilla_diagnostics.json"
    fi
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

# ── monitor ──────────────────────────────────────────────────────────────────
monitor)
    hdr "LIVE MONITOR (Ctrl+C to exit)"
    require_venv
    mkdir -p "$ROOT/logs"

    ACTIVE_LOG="$LOG"
    if [[ -f "$ROOT/engine_stdout.log" ]]; then
        ACTIVE_LOG="$ROOT/engine_stdout.log"
    elif [[ -f "$LOG" ]]; then
        ACTIVE_LOG="$LOG"
    else
        touch "$ROOT/engine_stdout.log"
        ACTIVE_LOG="$ROOT/engine_stdout.log"
    fi

    NARR_FILE="$ROOT/narration.jsonl"
    if [[ ! -f "$NARR_FILE" ]]; then
        NARR_FILE="$ROOT/logs/narration.jsonl"
    fi

    info "Log source: $ACTIVE_LOG"
    info "Narration source: $NARR_FILE"
    TZ_LABEL="America/New_York"
    LAST_SCAN_FILE="/tmp/rbot_last_scan_key"

    while true; do
        echo ""
        echo "════════════════════════════════════════════════════════════════════════════"
        echo "$(TZ="$TZ_LABEL" date '+%Y-%m-%d %I:%M:%S %p %Z')  |  RBOTZILLA LIVE UPDATE"
        echo "════════════════════════════════════════════════════════════════════════════"

        if pgrep -f "headless_runtime.py" >/dev/null 2>&1 && pgrep -f "oanda_trading_engine.py" >/dev/null 2>&1; then
            echo "System status: Trading engine is running normally."
        elif pgrep -f "headless_runtime.py" >/dev/null 2>&1; then
            echo "System status: Supervisor is running, but trading engine is not active."
        else
            echo "System status: Trading system is currently offline."
        fi

        echo ""
        last_conn=$(tail -n 250 "$ACTIVE_LOG" 2>/dev/null | grep -E "CONNECTION LOST|Attempting to reconnect|SYSTEM ON|OANDA.*READY|Connection resilience" | tail -n 1 || true)
        if [[ "$last_conn" == *"CONNECTION LOST"* ]]; then
            echo "Connection: Lost. The bot is trying to reconnect automatically."
        elif [[ "$last_conn" == *"Attempting to reconnect"* ]]; then
            echo "Connection: Reconnecting now."
        elif [[ "$last_conn" == *"SYSTEM ON"* || "$last_conn" == *"READY"* ]]; then
            echo "Connection: Healthy and connected to OANDA."
        else
            echo "Connection: No recent connection event to report."
        fi

        recent_hedge_markers=$(tail -n 400 "$ACTIVE_LOG" 2>/dev/null || true)
        if echo "$recent_hedge_markers" | grep -q "Quantitative Hedge Engine loaded"; then
            echo "Hedging engine: Active (loaded)."
        elif echo "$recent_hedge_markers" | grep -q "Hedge Engine not available"; then
            echo "Hedging engine: Not available (module not loaded)."
        else
            echo "Hedging engine: Status unknown (no startup marker found)."
        fi

        echo ""
        echo "[PLAIN ENGLISH ACTIVITY]"
        NARR_FILE_PATH="$NARR_FILE" TZ_LABEL="$TZ_LABEL" LAST_SCAN_FILE="$LAST_SCAN_FILE" "$PYTHON" - << 'PYEOF' || true
import json, os
from pathlib import Path
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

def to_local(ts_raw: str, tz_name: str) -> str:
    if not ts_raw:
        return ""
    try:
        ts = ts_raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if ZoneInfo is not None:
            dt = dt.astimezone(ZoneInfo(tz_name))
        return dt.strftime("%Y-%m-%d %I:%M:%S %p %Z")
    except Exception:
        return ts_raw[:19]

path = Path(os.environ.get("NARR_FILE_PATH", ""))
tz_name = os.environ.get("TZ_LABEL", "America/New_York")
last_scan_file = Path(os.environ.get("LAST_SCAN_FILE", "/tmp/rbot_last_scan_key"))
if not path.exists():
    print("No narration events yet.")
    raise SystemExit

events = []
with path.open() as f:
    for raw in f:
        try:
            events.append(json.loads(raw))
        except Exception:
            pass

if not events:
    print("No narration events yet.")
    raise SystemExit

latest_scan = next((e for e in reversed(events) if e.get("event_type") == "SIGNAL_SCAN_RESULTS"), None)
scan_dt = None
if latest_scan:
    scan_ts = latest_scan.get("timestamp") or latest_scan.get("ts") or ""
    try:
        scan_dt = datetime.fromisoformat(scan_ts.replace("Z", "+00:00")) if scan_ts else None
        if scan_dt and scan_dt.tzinfo is None:
            scan_dt = scan_dt.replace(tzinfo=timezone.utc)
    except Exception:
        scan_dt = None
    scan_key = scan_ts
    prev_key = ""
    try:
        if last_scan_file.exists():
            prev_key = last_scan_file.read_text().strip()
    except Exception:
        pass

    if scan_key and scan_key == prev_key:
        print(f"No new scan yet. Last update: {to_local(scan_ts, tz_name)}")
        raise SystemExit

    try:
        if scan_key:
            last_scan_file.write_text(scan_key)
    except Exception:
        pass

    det = latest_scan.get("details", {})
    scanned = det.get("pairs_scanned", 0)
    passed = det.get("candidates_passed", 0)
    placing = det.get("placing", 0)
    gate = det.get("min_conf_gate", 0.0)
    print(f"Scan time ({tz_name}): {to_local(scan_ts, tz_name)}")
    print(f"Scan summary: Checked {scanned} pairs. {passed} passed quality gates. Planning {placing} trade(s). Confidence gate is {float(gate)*100:.1f}%.")

    top_cands = det.get("top_candidates", [])[:3]
    if top_cands:
        print("Best opportunities:")
        for c in top_cands:
            sym = c.get("symbol", "?")
            dr = c.get("dir", "?")
            conf = float(c.get("conf", 0.0)) * 100
            votes = c.get("votes", 0)
            detectors = ", ".join(c.get("detectors", [])) or "unknown"
            print(f"  - {sym} {dr} at {conf:.1f}% confidence from {votes} strategy vote(s): {detectors}.")

    top_rej = det.get("top_rejected", [])[:5]
    if top_rej:
        print("Rejected pairs:")
        for r in top_rej:
            sym = r.get("symbol", "?")
            reason = r.get("reason", "rejected")
            conf = r.get("conf")
            direction = r.get("dir") or ""
            if conf is not None:
                conf_txt = f"{float(conf)*100:.1f}%"
            else:
                conf_txt = "n/a"

            if reason == "no_signal":
                print(f"  - {sym}: no confirmed setup this cycle (best estimate {conf_txt} {direction}).")
            elif reason == "confidence_below_threshold":
                print(f"  - {sym}: setup found at {conf_txt} {direction}, but below required gate.")
            elif reason == "already_active_symbol":
                print(f"  - {sym}: skipped because this symbol already has an open position.")
            else:
                print(f"  - {sym}: {reason} (confidence {conf_txt} {direction}).")

    stage_counts = det.get("rejected_by_stage") or {}
    if stage_counts:
        parts = ", ".join(f"{k}:{v}" for k, v in sorted(stage_counts.items()))
        print(f"Gate blocks by stage: {parts}.")

managed = [e for e in events[-80:] if e.get("event_type") in {
    "TRAILING_SL_SET", "TRAILING_SL_UPDATED", "TRAIL_TIGHT_SET", "FORCED_CLOSE", "POSITION_CLOSED", "SCALE_OUT_HALF", "SL_MOVED_BE", "GREEN_LOCK_ENFORCED", "PAIR_LIMIT_REJECTION"
}]
if scan_dt is not None:
    filtered_managed = []
    for e in managed:
        evt_ts = e.get("timestamp") or e.get("ts") or ""
        try:
            evt_dt = datetime.fromisoformat(evt_ts.replace("Z", "+00:00")) if evt_ts else None
            if evt_dt and evt_dt.tzinfo is None:
                evt_dt = evt_dt.replace(tzinfo=timezone.utc)
        except Exception:
            evt_dt = None
        if evt_dt is not None and evt_dt >= scan_dt:
            filtered_managed.append(e)
    managed = filtered_managed
if managed:
    print("Trade management activity:")
    for e in managed[-5:]:
        ts_raw = (e.get("timestamp") or e.get("ts") or "")
        ts = to_local(ts_raw, tz_name)
        evt = e.get("event_type", "")
        sym = e.get("symbol", "")
        print(f"  - {ts}: {evt} on {sym}.")
else:
    print("Trade management activity: no close/reallocate action in recent events.")

hedge_events = [e for e in events if "HEDGE" in str(e.get("event_type", "")).upper()]
if scan_dt is not None:
    filtered_hedge_events = []
    for e in hedge_events:
        evt_ts = e.get("timestamp") or e.get("ts") or ""
        try:
            evt_dt = datetime.fromisoformat(evt_ts.replace("Z", "+00:00")) if evt_ts else None
            if evt_dt and evt_dt.tzinfo is None:
                evt_dt = evt_dt.replace(tzinfo=timezone.utc)
        except Exception:
            evt_dt = None
        if evt_dt is not None and evt_dt >= scan_dt:
            filtered_hedge_events.append(e)
    hedge_events = filtered_hedge_events
if hedge_events:
    print(f"Quant hedging: {len(hedge_events)} hedge action(s) triggered for current scan window.")
else:
    print("Quant hedging: no hedge action triggered for current scan window.")
PYEOF

        echo ""
        echo "[ACTIVE TRADES]"
        if [[ -f "$ROOT/scripts/check_positions.py" ]]; then
            "$PYTHON" "$ROOT/scripts/check_positions.py" 2>/dev/null || warn "check_positions.py returned non-zero (continuing)"
        else
            warn "check_positions.py not found"
        fi

        if ! pgrep -f "oanda_trading_engine.py" >/dev/null 2>&1; then
            if pgrep -f "headless_runtime.py" >/dev/null 2>&1; then
                warn "Engine is temporarily down; supervisor is active and auto-restart is expected."
            else
                warn "Engine is down and supervisor is not running. Use Start Autonomous Engine to recover."
            fi
        fi
        echo "────────────────────────────────────────────────────────────────────────────"
        sleep 5
    done
    ;;

# ── monitor-tmux ─────────────────────────────────────────────────────────────
monitor-tmux)
    hdr "TMUX MONITOR DASHBOARD"
    require_venv
    if ! command -v tmux >/dev/null 2>&1; then
        err "tmux is not installed. Install with: sudo apt install -y tmux"
        exit 1
    fi

    SESSION="rbotzilla"
    tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"

    tmux new-session -d -s "$SESSION" -n "ops" "cd '$ROOT' && bash scripts/rbot_ctl.sh monitor"
    tmux new-window -t "$SESSION" -n "logs" "cd '$ROOT' && bash scripts/rbot_ctl.sh logs"
    tmux new-window -t "$SESSION" -n "narration" "cd '$ROOT' && bash scripts/rbot_ctl.sh logs-narration"
    tmux new-window -t "$SESSION" -n "status" "cd '$ROOT' && while true; do bash scripts/rbot_ctl.sh status; sleep 15; clear; done"

    ok "tmux dashboard started: $SESSION"
    info "Attach with: tmux attach -t $SESSION"
    ;;

# ── edge-kpi ────────────────────────────────────────────────────────────────
edge-kpi)
    hdr "EDGE KPI REPORT (ET DAY)"
    require_venv
    if [[ -f "$ROOT/scripts/edge_kpi_report_et.py" ]]; then
        "$PYTHON" "$ROOT/scripts/edge_kpi_report_et.py"
    else
        err "scripts/edge_kpi_report_et.py not found"
        exit 1
    fi
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
    echo "    start-auto       Start by current runtime mode (PAPER/LIVE)"
    echo "    stop             Stop all RBOTzilla processes"
    echo "    shutdown         Alias for stop"
    echo "    restart          Stop + start"
    echo "    refresh          Restart + diagnostics sweep"
    echo "    status           Show running processes + current mode"
    echo ""
    echo "  Diagnostics:"
    echo "    verify           Full system check (verify_system.py)"
    echo "    diagnostics      Manual systems + API checks + JSON export"
    echo "    check-api        OANDA API ping + account balance"
    echo "    check-positions  Open trades + unrealised PnL"
    echo ""
    echo "  Logs:"
    echo "    logs             Tail live engine log (Ctrl+C to exit)"
    echo "    logs-narration   Last 30 narration events"
    echo "    monitor          Live health + signal + P&L monitor"
    echo "    monitor-tmux     Persistent tmux monitor dashboard"
    echo "    edge-kpi         ET-day capital amplification KPI report"
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
