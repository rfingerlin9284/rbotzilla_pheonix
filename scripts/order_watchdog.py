#!/usr/bin/env python3
"""
RBOTZILLA ORDER WATCHDOG
========================
Background agent that monitors the live log in real-time for any
order/SL/TP problems the main bot missed or failed to handle.

Runs independently in its own tmux pane — NEVER touches the trading engine.
If it finds a critical issue it:
  1. Prints a loud alert to its own terminal
  2. Writes to logs/watchdog_alerts.log
  3. Sends SMS via sms_client (if configured)
  4. For SL_SELF_HEAL_FAILED: attempts emergency SL placement via OANDA API

Run:
  python scripts/order_watchdog.py

Or via rbot_ctl.sh:
  bash scripts/rbot_ctl.sh watchdog
"""

import os, sys, time, json, re, requests
from datetime import datetime, timezone
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
LOG_FILE    = ROOT / "logs" / "oanda_headless.log"
ALERT_LOG   = ROOT / "logs" / "watchdog_alerts.log"
ENV_FILE    = ROOT / ".env"
POLL_SECS   = 2       # how often to check for new log lines
TAIL_LINES  = 0       # start from current end of file (0 = tail mode)

# ── Load env -----------------------------------------------------------------
def _load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()

API_TOKEN  = os.getenv("OANDA_TOKEN") or os.getenv("OANDA_PRACTICE_TOKEN")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID") or os.getenv("OANDA_PRACTICE_ACCOUNT_ID")
API_BASE   = "https://api-fxpractice.oanda.com"
HEADERS    = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

# ── Alert patterns ────────────────────────────────────────────────────────────
# Each entry: (regex_pattern, severity, short_label, auto_action)
PATTERNS = [
    # 🔴 CRITICAL — trade running with no stop loss
    (r"SL SELF-HEAL FAILED.*trade=(\S+).*price=([0-9.]+)",
     "CRITICAL", "NO_STOP_LOSS", "emergency_sl"),

    # 🔴 CRITICAL — SL rejection (original precision bug)
    (r"PRICE_PRECISION_EXCEEDED.*tradeID.*?\"(\d+)\".*?price.*?\"([0-9.]+)\"",
     "CRITICAL", "SL_PRECISION_REJECTED", "emergency_sl"),

    # 🟠 HIGH — loss hedge fired (multiplies losses)
    (r"LOSS_HEDGE_TRIGGERED (\S+).*uPnL=(-[0-9.]+)",
     "HIGH", "LOSS_HEDGE_FIRED", None),

    # 🟠 HIGH — margin blown
    (r"POST-UPSIZE MARGIN CAP: ([0-9.]+)%",
     "HIGH", "MARGIN_CAP_BREACHED", None),

    # 🟡 MEDIUM — guardian gate blocked repeatedly
    (r"GUARDIAN GATE BLOCKED: margin_cap_would_exceed: ([0-9.]+)%",
     "MEDIUM", "MARGIN_GATE_BLOCK", None),

    # 🟡 MEDIUM — API timeout
    (r"OANDA API TIMEOUT.*?([0-9.]+)ms",
     "MEDIUM", "API_TIMEOUT", None),

    # 🟡 MEDIUM — bot stopped trading unexpectedly
    (r"BOT STATUS UPDATE - Is Trading: False",
     "LOW", "BOT_NOT_TRADING", None),

    # ℹ️ INFO — SL self-healed successfully
    (r"SL self-healed for (\S+):",
     "INFO", "SL_SELF_HEALED", None),
]

# ── OANDA emergency SL helper ─────────────────────────────────────────────────
def _emergency_set_sl(trade_id: str, fallback_price: str):
    """Last-resort SL placement when self-heal in the bot itself failed."""
    if not API_TOKEN or not ACCOUNT_ID:
        return False
    for decimals in [3, 5, 2]:
        try:
            price = f"{float(fallback_price):.{decimals}f}"
            resp = requests.put(
                f"{API_BASE}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}/orders",
                headers=HEADERS,
                json={"stopLoss": {"price": price}},
                timeout=10,
            )
            if resp.status_code == 200:
                return price
        except Exception:
            pass
    return False

# ── SMS alert ─────────────────────────────────────────────────────────────────
def _sms(message: str):
    try:
        sys.path.insert(0, str(ROOT))
        from util.sms_client import send_sms
        send_sms(message[:160])
    except Exception:
        pass  # SMS is best-effort

# ── Alert logger ──────────────────────────────────────────────────────────────
SEVERITY_COLORS = {
    "CRITICAL": "\033[91m\033[1m",  # bold red
    "HIGH":     "\033[93m\033[1m",  # bold yellow
    "MEDIUM":   "\033[93m",         # yellow
    "LOW":      "\033[96m",         # cyan
    "INFO":     "\033[92m",         # green
}
RESET = "\033[0m"

def alert(severity: str, label: str, detail: str, auto_action_result: str = ""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = SEVERITY_COLORS.get(severity, "")
    line = f"[{ts}] {severity:8s} | {label:30s} | {detail}"
    if auto_action_result:
        line += f" | AUTO: {auto_action_result}"

    # Terminal
    print(f"{color}{line}{RESET}")

    # File
    with open(ALERT_LOG, "a") as f:
        f.write(line + "\n")

    # SMS for critical only
    if severity == "CRITICAL":
        _sms(f"RBOT CRITICAL: {label} — {detail[:100]}")

# ── Recent alert dedup ────────────────────────────────────────────────────────
_recent_alerts: dict = {}
def _is_duplicate(key: str, cooldown_secs: int = 120) -> bool:
    now = time.time()
    last = _recent_alerts.get(key, 0)
    if now - last < cooldown_secs:
        return True
    _recent_alerts[key] = now
    return False

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    print(f"\033[1m\033[96m{'='*70}\033[0m")
    print(f"\033[1m\033[96m  RBOTZILLA ORDER WATCHDOG — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\033[0m")
    print(f"\033[1m\033[96m  Monitoring: {LOG_FILE}\033[0m")
    print(f"\033[1m\033[96m  Alerts: {ALERT_LOG}\033[0m")
    print(f"\033[1m\033[96m{'='*70}\033[0m\n")

    if not LOG_FILE.exists():
        print(f"⚠️  Log file not found: {LOG_FILE}")
        print("    Waiting for bot to start...")

    compiled = [(re.compile(p), sev, lbl, act) for p, sev, lbl, act in PATTERNS]
    last_pos = 0

    # Seek to end of file (tail mode)
    if LOG_FILE.exists():
        last_pos = LOG_FILE.stat().st_size

    print(f"  Watching from byte offset {last_pos:,} — tailing new output only\n")

    while True:
        try:
            if not LOG_FILE.exists():
                time.sleep(POLL_SECS)
                continue

            current_size = LOG_FILE.stat().st_size
            if current_size < last_pos:
                # Log was rotated/truncated
                last_pos = 0

            if current_size > last_pos:
                with open(LOG_FILE, "rb") as f:
                    f.seek(last_pos)
                    new_bytes = f.read(current_size - last_pos)
                last_pos = current_size

                # Strip ANSI color codes for pattern matching
                text = new_bytes.decode("utf-8", errors="replace")
                clean = re.sub(r'\x1b\[[0-9;]*m', '', text)

                for line in clean.splitlines():
                    if not line.strip():
                        continue
                    for pattern, severity, label, action in compiled:
                        m = pattern.search(line)
                        if not m:
                            continue
                        groups = m.groups()
                        detail = " | ".join(groups) if groups else line[:120].strip()
                        dedup_key = f"{label}:{groups[0] if groups else ''}"

                        if _is_duplicate(dedup_key, cooldown_secs=60):
                            continue

                        auto_result = ""

                        # Auto-actions
                        if action == "emergency_sl" and len(groups) >= 2:
                            trade_id, price = groups[0], groups[1]
                            healed_price = _emergency_set_sl(trade_id, price)
                            if healed_price:
                                auto_result = f"EMERGENCY SL SET @ {healed_price} ✅"
                            else:
                                auto_result = "EMERGENCY SL FAILED ❌"

                        alert(severity, label, detail, auto_result)

        except KeyboardInterrupt:
            print("\n\033[93m  Watchdog stopped by user.\033[0m")
            break
        except Exception as e:
            print(f"\033[91m  Watchdog error: {e}\033[0m")

        time.sleep(POLL_SECS)

if __name__ == "__main__":
    main()
