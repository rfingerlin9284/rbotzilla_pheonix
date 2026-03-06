#!/usr/bin/env python3
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
NARRATION = ROOT / "narration.jsonl"
TRACKING = ROOT / "logs" / "daily_profit_tracking.jsonl"
ET = ZoneInfo("America/New_York")

MGMT_EVENTS = {
    "SL_MOVED_BE",
    "GREEN_LOCK_ENFORCED",
    "SCALE_OUT_HALF",
    "TRAIL_TIGHT_SET",
    "TRAILING_SL_SET",
    "TRAILING_SL_UPDATED",
    "FORCED_CLOSE",
    "HARD_DOLLAR_STOP",
    "POSITION_CLOSED",
}


def parse_ts(raw: str):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def in_today_et(dt: datetime, today_et):
    return dt.astimezone(ET).date() == today_et


def load_narration(today_et):
    event_counts = Counter()
    gate_reasons = Counter()

    trade_open_ts = {}
    trade_events = defaultdict(set)
    first_mgmt_minutes = []

    if not NARRATION.exists():
        return event_counts, gate_reasons, trade_open_ts, trade_events, first_mgmt_minutes

    with NARRATION.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except Exception:
                continue

            dt = parse_ts(ev.get("timestamp") or ev.get("ts"))
            if not dt or not in_today_et(dt, today_et):
                continue

            etype = str(ev.get("event_type") or "")
            event_counts[etype] += 1

            details = ev.get("details") or {}
            symbol = str(ev.get("symbol") or details.get("symbol") or "").upper()
            trade_id = str(details.get("trade_id") or details.get("order_id") or "").strip()
            key = f"{symbol}:{trade_id or 'unknown'}"

            if etype == "TRADE_OPENED":
                trade_open_ts[key] = dt
                trade_events[key].add("TRADE_OPENED")

            if etype == "GATE_REJECTION":
                gate_reasons[str(details.get("reason") or "unknown")] += 1

            if etype in MGMT_EVENTS:
                trade_events[key].add(etype)
                open_dt = trade_open_ts.get(key)
                if open_dt and "__first_mgmt_recorded__" not in trade_events[key]:
                    mins = max(0.0, (dt - open_dt).total_seconds() / 60.0)
                    first_mgmt_minutes.append(mins)
                    trade_events[key].add("__first_mgmt_recorded__")

    return event_counts, gate_reasons, trade_open_ts, trade_events, first_mgmt_minutes


def load_realized_today(today_et):
    rows = []
    if not TRACKING.exists():
        return rows

    with TRACKING.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            dt = parse_ts(rec.get("timestamp"))
            if not dt or not in_today_et(dt, today_et):
                continue
            rows.append(rec)

    return rows


def main():
    today_et = datetime.now(ET).date()
    (
        event_counts,
        gate_reasons,
        trade_open_ts,
        trade_events,
        first_mgmt_minutes,
    ) = load_narration(today_et)

    realized_rows = load_realized_today(today_et)

    opened_keys = set(trade_open_ts.keys())
    opened = len(opened_keys)

    def count_with(event_name):
        return sum(1 for k in opened_keys if event_name in trade_events.get(k, set()))

    be = count_with("SL_MOVED_BE")
    green = count_with("GREEN_LOCK_ENFORCED")
    scale = count_with("SCALE_OUT_HALF")
    trail = sum(
        1
        for k in opened_keys
        if (
            "TRAIL_TIGHT_SET" in trade_events.get(k, set())
            or "TRAILING_SL_SET" in trade_events.get(k, set())
            or "TRAILING_SL_UPDATED" in trade_events.get(k, set())
        )
    )
    terminal = sum(
        1
        for k in opened_keys
        if (
            "FORCED_CLOSE" in trade_events.get(k, set())
            or "HARD_DOLLAR_STOP" in trade_events.get(k, set())
            or "POSITION_CLOSED" in trade_events.get(k, set())
        )
    )
    no_mgmt = sum(
        1
        for k in opened_keys
        if not (trade_events.get(k, set()) & MGMT_EVENTS)
    )

    median_mgmt = None
    if first_mgmt_minutes:
        xs = sorted(first_mgmt_minutes)
        n = len(xs)
        median_mgmt = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0

    wins = sum(1 for r in realized_rows if float(r.get("pnl_usd", 0.0)) > 0)
    losses = sum(1 for r in realized_rows if float(r.get("pnl_usd", 0.0)) <= 0)
    total_realized = sum(float(r.get("pnl_usd", 0.0)) for r in realized_rows)
    avg_win = (
        sum(float(r.get("pnl_usd", 0.0)) for r in realized_rows if float(r.get("pnl_usd", 0.0)) > 0) / wins
        if wins else 0.0
    )
    avg_loss = (
        abs(sum(float(r.get("pnl_usd", 0.0)) for r in realized_rows if float(r.get("pnl_usd", 0.0)) <= 0) / losses)
        if losses else 0.0
    )
    win_rate = (wins / len(realized_rows)) if realized_rows else 0.0
    expectancy = (win_rate * avg_win) - ((1.0 - win_rate) * avg_loss) if realized_rows else 0.0

    print("=" * 92)
    print(f"RBOT EDGE KPI REPORT (ET): {today_et}")
    print("=" * 92)
    print(f"Trades opened: {opened}")
    print(
        f"Lifecycle conversion: BE={be} ({(be/opened*100):.1f}% if opened else 0), "
        f"GreenLock={green} ({(green/opened*100):.1f}% if opened else 0), "
        f"ScaleOut={scale} ({(scale/opened*100):.1f}% if opened else 0), "
        f"Trail={trail} ({(trail/opened*100):.1f}% if opened else 0), "
        f"Terminal={terminal} ({(terminal/opened*100):.1f}% if opened else 0)"
    )
    print(f"Opened with no management event: {no_mgmt}")
    if median_mgmt is not None:
        print(f"Median minutes to first management action: {median_mgmt:.2f}m")
    else:
        print("Median minutes to first management action: n/a")

    print("\nRealized expectancy (today ET):")
    print(
        f"Closed trades={len(realized_rows)} | Wins={wins} | Losses={losses} | "
        f"WinRate={win_rate*100:.1f}% | AvgWin=${avg_win:.2f} | AvgLoss=${avg_loss:.2f} | "
        f"Expectancy=${expectancy:.2f} | RealizedPnL=${total_realized:.2f}"
    )

    print("\nTop gate blockers:")
    if gate_reasons:
        for reason, count in gate_reasons.most_common(8):
            print(f"- {reason}: {count}")
    else:
        print("- none")

    print("\nHigh-level event counts:")
    for k, v in event_counts.most_common(12):
        print(f"- {k}: {v}")


if __name__ == "__main__":
    main()
