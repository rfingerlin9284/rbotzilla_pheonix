#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          RBOTZILLA PHOENIX — NARRATION LIVE  (Plain English Feed)           ║
║  Shows: Connection status | Open trades | OCO orders | Agent dialogs        ║
║  Usage: python scripts/narration_live.py [--refresh 5]                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, sys, json, time, signal, argparse, subprocess, textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── path setup ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NARRATION_FILE   = ROOT / "narration.jsonl"
OANDA_LOG        = ROOT / "logs" / "oanda_headless.log"
FALLBACK_NARR    = ROOT / "logs" / "narration.jsonl"

# ── ANSI colours ─────────────────────────────────────────────────────────────
R  = "\033[0m"
B  = "\033[1m"
DIM= "\033[2m"
CY = "\033[96m"
GR = "\033[92m"
YE = "\033[93m"
RE = "\033[91m"
MA = "\033[95m"
BL = "\033[94m"
WH = "\033[97m"
BG_DARK  = "\033[40m"
BG_GREEN = "\033[42m"
BG_RED   = "\033[41m"

# ── helpers ───────────────────────────────────────────────────────────────────
def cls():   print("\033[H\033[2J\033[3J", end="", flush=True)
def hr(c="═", w=80): print(f"{DIM}{c*w}{R}")
def now_et():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now()

def wrap(text:str, width:int=76, indent:str="    ") -> str:
    return textwrap.fill(text, width=width, subsequent_indent=indent)

# ── process / connection checks ───────────────────────────────────────────────
def is_engine_running() -> tuple[bool,bool]:
    """Returns (supervisor_up, engine_up)"""
    sup = bool(subprocess.run(
        ["pgrep","-f","headless_runtime.py"],
        capture_output=True).stdout.strip())
    eng = bool(subprocess.run(
        ["pgrep","-f","oanda_trading_engine.py"],
        capture_output=True).stdout.strip())
    return sup, eng

def get_oanda_log_snippet() -> str:
    """Grab the last few lines from the OANDA log for connection status."""
    try:
        result = subprocess.run(
            ["tail","-n","400", str(OANDA_LOG)], capture_output=True, text=True)
        return result.stdout
    except Exception:
        return ""

def detect_connection_status(log_snippet:str) -> tuple[str,str]:
    """Returns (status_label, colour)"""
    for line in reversed(log_snippet.splitlines()):
        if "CONNECTION LOST" in line:
            return "DISCONNECTED — Reconnecting…", RE
        if "Attempting to reconnect" in line:
            return "RECONNECTING NOW…", YE
        if ("SYSTEM ON" in line or "OANDA PRACTICE API connected" in line
                or "OANDA LIVE API connected" in line or "READY" in line):
            return "CONNECTED ✓", GR
    # check if engine is up at all
    sup, eng = is_engine_running()
    if eng:
        return "CONNECTED ✓", GR
    if sup:
        return "SUPERVISOR UP — Engine restarting…", YE
    return "OFFLINE", RE

# ── narration file reader ─────────────────────────────────────────────────────
def load_narration(n:int=120) -> list[dict]:
    path = NARRATION_FILE if NARRATION_FILE.exists() else FALLBACK_NARR
    if not path.exists():
        return []
    events = []
    try:
        with path.open() as f:
            for raw in f:
                try:
                    events.append(json.loads(raw))
                except Exception:
                    pass
    except Exception:
        pass
    return events[-n:]

# ── time formatting ────────────────────────────────────────────────────────────
def ts_to_et(ts_raw:str) -> str:
    if not ts_raw:
        return ""
    try:
        ts = ts_raw.replace("Z","+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            dt = dt.astimezone(ZoneInfo("America/New_York"))
        except Exception:
            pass
        return dt.strftime("%I:%M:%S %p")
    except Exception:
        return ts_raw[:19]

def ago(ts_raw:str) -> str:
    """Pretty elapsed time."""
    try:
        ts = ts_raw.replace("Z","+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = int((datetime.now(timezone.utc) - dt).total_seconds())
        if secs < 60:   return f"{secs}s ago"
        if secs < 3600: return f"{secs//60}m ago"
        return f"{secs//3600}h {(secs%3600)//60}m ago"
    except Exception:
        return ""

# ── plain-English translations ────────────────────────────────────────────────
EVENT_LABELS = {
    "TRADE_OPENED":           ("🟢 TRADE OPENED",          GR),
    "TRADE_CLOSED":           ("🔴 TRADE CLOSED",          RE),
    "POSITION_CLOSED":        ("🔴 POSITION CLOSED",       RE),
    "FORCED_CLOSE":           ("⛔ FORCED CLOSE",          RE+B),
    "SIGNAL_SCAN_RESULTS":    ("📡 MARKET SCAN",           CY),
    "GATE_REJECTION":         ("🚫 GATE BLOCKED",          YE),
    "PAIR_LIMIT_REJECTION":   ("🚫 PAIR LIMIT HIT",        YE),
    "BROKER_REGISTRY_BLOCK":  ("🚫 SYMBOL ALREADY OPEN",   YE),
    "TRAILING_SL_UPDATED":    ("📈 TRAILING STOP MOVED",   BL),
    "TRAILING_SL_SET":        ("📐 TRAILING STOP SET",     BL),
    "SL_MOVED_BE":            ("🛡️  BREAKEVEN LOCK",        GR),
    "GREEN_LOCK_ENFORCED":    ("🔒 GREEN LOCK",             GR),
    "SCALE_OUT_HALF":         ("💰 SCALE-OUT 50%",          GR),
    "TP_COOLDOWN_BLOCK":      ("⏸  TP COOLDOWN",           MA),
    "HIVE_CONSENSUS_STRONG":  ("🐝 HIVE STRONG CONSENSUS", MA),
    "HIVE_CONSENSUS_WEAK":    ("🐝 HIVE WEAK CONSENSUS",   DIM),
    "CHARTER_VIOLATION":      ("⚠️  CHARTER VIOLATION",     RE+B),
    "POSITION_POLICE_SUMMARY":("🚓 POSITION POLICE",       MA),
    "TRADE_ERROR":            ("❌ TRADE ERROR",            RE),
    "RR_ESCALATION":          ("🔧 RR ESCALATED",          YE),
    "UPSIZE_TO_MIN_NOTIONAL": ("📐 POSITION UPSIZED",      YE),
    "BOT_STOPPED_BY_USER":    ("🛑 BOT STOPPED",           RE+B),
    "TRADE_SIGNAL":           ("📊 SIGNAL FOUND",          CY),
    "TP_SL_VALIDATED":        ("✅ TP/SL VALIDATED",       GR),
    "SESSION_STATUS":         ("🕐 SESSION UPDATE",        DIM),
    "PROFILE_STATUS":         ("⚙️  PROFILE STATUS",        DIM),
}

def human_event(event:dict) -> Optional[str]:
    """Convert a narration event into a human-readable string."""
    etype = event.get("event_type","")
    sym   = event.get("symbol","") or ""
    det   = event.get("details",{}) or {}
    ts    = event.get("timestamp") or event.get("ts","")
    rick  = (event.get("rick_says") or "").strip()

    label, colour = EVENT_LABELS.get(etype, (f"ℹ️  {etype}", DIM))
    time_str = ts_to_et(ts)
    ago_str  = ago(ts)

    # ── build the narrative sentence ──────────────────────────────────────────
    if etype == "TRADE_OPENED":
        direction = det.get("direction","?")
        entry     = det.get("entry_price",0)
        sl        = det.get("stop_loss",0)
        tp        = det.get("take_profit",0)
        size      = det.get("size",0)
        notional  = det.get("notional",0)
        rr        = det.get("rr_ratio",0)
        conf      = (det.get("signal_confidence") or 0)
        dets_list = det.get("signal_detectors") or []
        dets      = ", ".join(dets_list) if dets_list else "—"
        narrative = (
            f"Entered {direction} on {sym} at {entry:.5f}. "
            f"Stop loss at {sl:.5f}, take profit at {tp:.5f}. "
            f"Position: {size:,} units (≈${notional:,.0f} notional). "
            f"R:R ratio {rr:.2f}:1 at {conf*100:.1f}% confidence via {dets}."
        )

    elif etype in ("TRADE_CLOSED","POSITION_CLOSED"):
        reason  = det.get("reason","") or det.get("status","—")
        pnl     = det.get("pnl") or det.get("realized_pnl") or 0
        pnl_str = f"+${pnl:.2f}" if pnl and pnl>0 else (f"-${abs(pnl):.2f}" if pnl else "")
        narrative = f"{sym} position closed. Reason: {reason}. {pnl_str}"

    elif etype == "FORCED_CLOSE":
        reason = det.get("reason", "Risk limit")
        narrative = f"{sym} was force-closed by the system. Reason: {reason}."

    elif etype == "SIGNAL_SCAN_RESULTS":
        scanned = det.get("pairs_scanned",0)
        passed  = det.get("candidates_passed",0)
        placing = det.get("placing",0)
        gate    = float(det.get("min_conf_gate",0))*100
        tops    = det.get("top_candidates",[])[:3]
        lines   = [
            f"Scanned {scanned} pairs. {passed} passed all quality gates. "
            f"Placing {placing} trade(s). Confidence gate: {gate:.1f}%."
        ]
        if tops:
            lines.append("Top setups found:")
            for c in tops:
                lines.append(
                    f"  • {c.get('symbol','?')} {c.get('dir','?')} — "
                    f"{float(c.get('conf',0))*100:.1f}% conf, "
                    f"{c.get('votes',0)} vote(s), "
                    f"detectors: {', '.join(c.get('detectors',[]))}"
                )
        narrative = "\n".join(lines)

    elif etype == "GATE_REJECTION":
        reason = det.get("reason","unknown")
        narrative = (
            f"{sym} trade was blocked before placement. "
            f"The guardian gate said: {reason}. No order was sent."
        )

    elif etype == "PAIR_LIMIT_REJECTION":
        narrative = (
            f"{sym} was skipped — the max number of simultaneous pairs has been reached. "
            f"Active pairs: {', '.join(det.get('active_pairs',[]) or [])}."
        )

    elif etype == "BROKER_REGISTRY_BLOCK":
        narrative = (
            f"{sym} is already open on another platform. "
            f"Skipping to avoid duplicate exposure."
        )

    elif etype in ("TRAILING_SL_UPDATED","TRAILING_SL_SET"):
        old = det.get("old_sl") or det.get("previous_sl","?")
        new = det.get("new_sl") or det.get("stop_loss","?")
        narrative = f"{sym} trailing stop moved from {old} → {new}."

    elif etype == "SL_MOVED_BE":
        be  = det.get("breakeven_price","?")
        narrative = f"{sym} stop loss locked to breakeven at {be}. Risk-free territory."

    elif etype == "GREEN_LOCK_ENFORCED":
        lock = det.get("lock_price","?")
        narrative = f"{sym} green-locked at {lock}. Trade cannot turn into a loss now."

    elif etype == "SCALE_OUT_HALF":
        pnl = det.get("pnl","?")
        narrative = f"{sym} scaled out 50% of the position. PnL so far: {pnl}."

    elif etype == "TP_COOLDOWN_BLOCK":
        remaining = det.get("remaining_seconds",0)
        narrative = (
            f"{sym} is in a post-TP cooldown. "
            f"The system is preventing re-entry for another {remaining}s to avoid chasing."
        )

    elif etype == "HIVE_CONSENSUS_STRONG":
        consensus = det.get("consensus","?")
        conf      = float(det.get("confidence",0))*100
        narrative = (
            f"The Hive Mind AI agents reached strong consensus on {sym}: {consensus} "
            f"at {conf:.1f}% confidence. Signal amplified and approved."
        )

    elif etype == "HIVE_CONSENSUS_WEAK":
        narrative = (
            f"The Hive Mind agents could not agree strongly on {sym}. "
            f"Signal returned without amplification."
        )

    elif etype == "CHARTER_VIOLATION":
        viol = det.get("violation","?")
        narrative = (
            f"Charter violation detected! Rule broken: {viol} on {sym}. "
            f"Order was blocked to preserve capital safety."
        )

    elif etype == "POSITION_POLICE_SUMMARY":
        found  = det.get("violations_found",0)
        closed = det.get("violations_closed",0)
        narrative = (
            f"Position Police sweep complete. "
            f"Found {found} under-notional position(s), closed {closed}."
        )

    elif etype == "TRADE_ERROR":
        err = det.get("error","unknown error")
        narrative = f"Error while placing trade on {sym}: {err}"

    elif etype == "RR_ESCALATION":
        orig = det.get("original_rr", 0)
        new  = det.get("escalated_rr", 0)
        narrative = (
            f"{sym} R:R was {orig:.2f}:1. "
            f"System auto-escalated take profit to meet the charter's {new:.2f}:1 minimum."
        )

    elif etype == "UPSIZE_TO_MIN_NOTIONAL":
        before = det.get("units_before",0)
        after  = det.get("units_after",0)
        nb     = det.get("notional_before",0)
        na     = det.get("notional_after",0)
        narrative = (
            f"{sym} position upsized from {before:,} → {after:,} units "
            f"(${nb:,.0f} → ${na:,.0f}) to meet the $15,000 charter minimum."
        )

    elif etype == "BOT_STOPPED_BY_USER":
        narrative = "Bot was cleanly stopped by user. All positions remain on broker."

    elif etype == "TRADE_SIGNAL":
        direction = det.get("direction","?")
        conf      = float(det.get("signal_confidence") or 0)*100
        narrative = (
            f"Signal detected: {sym} {direction} at {conf:.1f}% confidence. "
            f"Evaluating for entry…"
        )

    elif etype in ("SESSION_STATUS","PROFILE_STATUS"):
        return None   # suppress verbose internal events from main feed

    else:
        # Generic fallback
        summary = rick or str(det)[:120]
        narrative = summary

    # ── final block ───────────────────────────────────────────────────────────
    lines = [
        f"{colour}{B}{label}{R}   {DIM}{time_str}  ({ago_str}){R}",
        wrap(narrative, width=76),
    ]
    if rick and etype not in ("SESSION_STATUS","PROFILE_STATUS"):
        lines.append(f"  {MA}{DIM}💬 Rick: {rick}{R}")
    return "\n".join(lines)

# ── open positions (via check_positions.py) ───────────────────────────────────
def get_positions_summary() -> str:
    script = ROOT / "scripts" / "check_positions.py"
    if not script.exists():
        return f"  {DIM}check_positions.py not found.{R}"
    try:
        venv_py = ROOT / "venv" / "bin" / "python"
        py = str(venv_py) if venv_py.exists() else sys.executable
        result = subprocess.run(
            [py, str(script)], capture_output=True, text=True, timeout=12
        )
        out = (result.stdout or "").strip()
        if not out:
            return f"  {DIM}No output from check_positions.py{R}"
        return out
    except Exception as e:
        return f"  {RE}Error fetching positions: {e}{R}"

# ── agent dialog extraction from log ─────────────────────────────────────────
AGENT_KEYWORDS = [
    "🐝 Hive","🤖","[Agent]","[RiskAgent]","[AuditAgent]","[SentimentAgent]",
    "Hive amplified","Hive amplification","consensus","SWARM","node_id",
    "ML Intelligence","Momentum Profile","regime","Strategy Aggregator",
]

def extract_agent_dialogs(log:str, n:int=10) -> list[str]:
    out = []
    for line in log.splitlines():
        stripped = line.strip()
        if any(k in stripped for k in AGENT_KEYWORDS):
            # strip ANSI escape codes
            import re
            clean = re.sub(r'\x1b\[[0-9;]*m','', stripped)
            if clean:
                out.append(clean)
    return out[-n:]

# ── main display ─────────────────────────────────────────────────────────────
def render(args):
    cls()
    now_str = now_et().strftime("%Y-%m-%d  %I:%M:%S %p ET")
    print(f"{BL}{B}╔{'═'*78}╗{R}")
    print(f"{BL}{B}║{'RBOTZILLA PHOENIX  —  NARRATION LIVE':^78}║{R}")
    print(f"{BL}{B}║{now_str:^78}║{R}")
    print(f"{BL}{B}╚{'═'*78}╝{R}")

    # ── 1. CONNECTION STATUS ──────────────────────────────────────────────────
    sup, eng = is_engine_running()
    log_snip = get_oanda_log_snippet()
    conn_label, conn_colour = detect_connection_status(log_snip)

    print(f"\n{B}  🔌 CONNECTION STATUS{R}")
    hr("─")
    status_box = f"  {conn_colour}{B} {conn_label} {R}"
    if eng:
        status_box += f"   {GR}Supervisor ✓  Engine ✓{R}"
    elif sup:
        status_box += f"   {YE}Supervisor ✓  Engine ↻{R}"
    else:
        status_box += f"   {RE}Supervisor ✗  Engine ✗{R}"
    print(status_box)

    # ── 2. OPEN POSITIONS & OCO ORDERS ───────────────────────────────────────
    print(f"\n{B}  📋 OPEN POSITIONS & OCO ORDERS{R}")
    hr("─")
    positions_text = get_positions_summary()
    for line in positions_text.splitlines():
        print(f"  {line}")

    # ── 3. AGENT INTERNAL DIALOGS ─────────────────────────────────────────────
    agent_dialogs = extract_agent_dialogs(log_snip, n=12)
    if agent_dialogs:
        print(f"\n{B}  🤖 AGENT INTERNAL ACTIVITY (Plain English){R}")
        hr("─")
        print(f"  {DIM}These are the conversations between the AI agents and trading modules:{R}\n")
        for line in agent_dialogs:
            # Translate technical terms into plain English
            line = (line
                .replace("Hive amplified",    "🐝 [ HIVE MIND ] Agents agreed — signal amplified for")
                .replace("Hive amplification error", "🐝 [ HIVE MIND ] Agents couldn't reach agreement on")
                .replace("ML Intelligence",   "🤖 [ ML ENGINE ] Machine Learning module")
                .replace("Strategy Aggregator","📊 [ STRATEGIES ] Strategy vote aggregator")
                .replace("Momentum Profile",   "📈 [ MOMENTUM ] Momentum tracker")
                .replace("Regime Detector",    "🌐 [ REGIME ] Market regime detection")
                .replace("consensus",          "group vote")
            )
            print(f"  {MA}{DIM}{line}{R}")

    # ── 4. LIVE NARRATION EVENTS ──────────────────────────────────────────────
    print(f"\n{B}  📣 LIVE ACTIVITY NARRATION  (most recent {args.events} events){R}")
    hr("─")
    print(f"  {DIM}Everything the system is doing, explained in plain English:{R}\n")

    events = load_narration(n=300)

    # Filter: drop SESSION_STATUS / PROFILE_STATUS noise unless --verbose
    if not args.verbose:
        events = [e for e in events
                  if e.get("event_type") not in
                  ("SESSION_STATUS","PROFILE_STATUS","TP_SL_VALIDATED",
                   "HIVE_CONSENSUS_WEAK")]

    displayed = 0
    for ev in reversed(events):
        if displayed >= args.events:
            break
        rendered = human_event(ev)
        if rendered is None:
            continue
        for line in rendered.splitlines():
            print(f"  {line}")
        print()
        displayed += 1

    if displayed == 0:
        print(f"  {DIM}No narration events yet. Start the engine and trades will appear here.{R}\n")

    # ── 5. FOOTER ─────────────────────────────────────────────────────────────
    hr("═")
    print(f"  {DIM}Refreshing every {args.refresh}s  |  Press Ctrl+C to exit | --events N  --refresh N  --verbose{R}")

# ── entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="RBOTZILLA PHOENIX — Narration Live Display")
    parser.add_argument("--refresh", type=int, default=20,
                        help="Refresh interval in seconds (default 20)")
    parser.add_argument("--events",  type=int, default=20,
                        help="Number of narration events to show (default 20)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show all events including internal session/profile updates")
    parser.add_argument("--once", action="store_true",
                        help="Render once and exit (non-interactive)")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    
    paused = False
    
    # helper for non-blocking input
    import select
    
    try:
        while True:
            if not paused:
                render(args)
            
            if paused:
                # If paused, just draw a paused banner at the top/bottom if we want, but keeping it simple:
                print(f"\n{YE}{B} ⏸  REFRESH PAUSED. Press [SPACE] to resume, [R] to force refresh, [Q] to quit.{R}")
                
            if args.once:
                break
                
            # Wait for either timeout (args.refresh) or keyboard input
            # We use select on stdin
            timeout = args.refresh if not paused else 0.5
            i, o, e = select.select([sys.stdin], [], [], timeout)
            
            if i:
                # Key pressed
                key = sys.stdin.read(1).lower()
                if key == 'q':
                    break
                elif key == ' ':
                    paused = not paused
                    if not paused:
                        cls()
                        print(f"{GR}▶ Resuming refresh...{R}")
                        time.sleep(0.5)
                elif key == 'r':
                    # Force refresh even if paused
                    render(args)
            
    except KeyboardInterrupt:
        pass
    finally:
        cls()
        print(f"\n{YE}Narration Live stopped. Bot is still running in the background.{R}\n")

if __name__ == "__main__":
    import termios
    import tty
    
    # Setup terminal for raw single-character unbuffered input, but keep ^C working
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        main()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
