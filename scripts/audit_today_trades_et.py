#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


EVENTS = {
    "TRADE_OPENED",
    "SL_MOVED_BE",
    "GREEN_LOCK_ENFORCED",
    "TRAIL_TIGHT_SET",
    "TRAILING_SL_SET",
    "TRAILING_SL_UPDATED",
    "SCALE_OUT_HALF",
    "HARD_DOLLAR_STOP",
    "FORCED_CLOSE",
    "POSITION_CLOSED",
}


def parse_ts(raw: str):
    try:
        dt = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Audit today's trade lifecycle in US/Eastern")
    parser.add_argument("--file", default="narration.jsonl", help="Path to narration jsonl")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")

    eastern = ZoneInfo("America/New_York")
    today_et = datetime.now(eastern).date()

    grouped = defaultdict(list)
    total_events = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except Exception:
                continue

            etype = ev.get("event_type")
            if etype not in EVENTS:
                continue

            dt = parse_ts(ev.get("timestamp") or ev.get("ts"))
            if not dt:
                continue
            if dt.astimezone(eastern).date() != today_et:
                continue

            details = ev.get("details") or {}
            symbol = (ev.get("symbol") or details.get("symbol") or "").upper()
            trade_id = str(details.get("trade_id") or details.get("order_id") or "")
            key = f"{symbol}:{trade_id or 'unknown'}"

            grouped[key].append({
                "timestamp_utc": dt.astimezone(timezone.utc).isoformat(),
                "timestamp_et": dt.astimezone(eastern).isoformat(),
                "event_type": etype,
                "symbol": symbol,
                "trade_id": trade_id or None,
                "entry": details.get("entry") or details.get("entry_price"),
                "old_sl": details.get("old_sl") or details.get("prior_stop"),
                "new_sl": details.get("new_sl") or details.get("set_stop"),
                "green_lock_applied": details.get("green_lock_applied"),
                "reason": details.get("reason"),
            })
            total_events += 1

    for key in grouped:
        grouped[key].sort(key=lambda e: e["timestamp_utc"])

    output = {
        "date_et": str(today_et),
        "timezone": "America/New_York",
        "trade_groups": len(grouped),
        "events": total_events,
        "groups": grouped,
    }

    if args.json:
        print(json.dumps(output, indent=2, default=list))
        return

    print("=" * 88)
    print(f"RBOT TRADE AUDIT (ET day): {today_et}  |  groups={len(grouped)}  events={total_events}")
    print("=" * 88)
    if not grouped:
        print("No matching trade lifecycle events found for today (ET).")
        return

    for key, rows in grouped.items():
        symbol, trade_id = key.split(":", 1)
        print(f"\n{symbol}  trade_id={trade_id}")
        for row in rows:
            print(
                f"  {row['timestamp_et']}  {row['event_type']:<18} "
                f"entry={row['entry']} old_sl={row['old_sl']} new_sl={row['new_sl']} "
                f"green_lock={row['green_lock_applied']} reason={row['reason']}"
            )


if __name__ == "__main__":
    main()
