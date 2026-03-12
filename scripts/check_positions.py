#!/usr/bin/env python3
"""scripts/check_positions.py — OANDA position snapshot"""
import os, sys, json, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Load creds from root .env (where the real values live)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

TOKEN      = os.getenv("OANDA_PRACTICE_TOKEN") or os.getenv("OANDA_API_KEY", "")
ACCOUNT_ID = os.getenv("OANDA_PRACTICE_ACCOUNT_ID") or os.getenv("OANDA_ACCOUNT_ID", "")
BASE       = "https://api-fxpractice.oanda.com"
HDR        = {"Authorization": f"Bearer {TOKEN}"}

def _load_trade_opened_metadata():
    """Best-effort parse of narration + engine metadata for trade context."""
    by_trade_id = {}
    by_order_id = {}
    by_symbol = {}
    narration_path = os.path.join(ROOT, "narration.jsonl")

    def _merge(details):
        if not isinstance(details, dict):
            return
        trade_id = str(details.get("trade_id") or details.get("tradeID") or details.get("id") or "").strip()
        order_id = str(details.get("order_id") or details.get("orderID") or "").strip()
        symbol = str(details.get("symbol") or "").strip().upper()
        if trade_id:
            by_trade_id[trade_id] = details
        if order_id:
            by_order_id[order_id] = details
        if symbol:
            by_symbol[symbol] = details

    if os.path.exists(narration_path):
        try:
            with open(narration_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue

                    event_type = str(obj.get("event_type") or "")
                    if event_type not in {"TRADE_OPENED", "OCO_PLACED"}:
                        continue

                    details = obj.get("details") if isinstance(obj.get("details"), dict) else {}
                    if not details:
                        continue

                    if "symbol" not in details and obj.get("symbol"):
                        details["symbol"] = obj.get("symbol")
                    _merge(details)
        except Exception:
            pass

    metadata_index_path = os.path.join(ROOT, "logs", "trade_metadata_index.json")
    if os.path.exists(metadata_index_path):
        try:
            with open(metadata_index_path, "r", encoding="utf-8") as fh:
                idx = json.load(fh)
            if isinstance(idx, dict):
                for value in (idx.get("by_trade_id") or {}).values():
                    _merge(value if isinstance(value, dict) else {})
                for value in (idx.get("by_order_id") or {}).values():
                    _merge(value if isinstance(value, dict) else {})
                for value in (idx.get("by_symbol") or {}).values():
                    _merge(value if isinstance(value, dict) else {})
        except Exception:
            pass

    return by_trade_id, by_order_id, by_symbol


def _fmt_unknown(value):
    if value is None:
        return "unknown"
    if isinstance(value, str) and value.strip() == "":
        return "unknown"
    if isinstance(value, (list, tuple, set)) and len(value) == 0:
        return "unknown"
    return value

def _to_float_or_none(value):
    try:
        if value in (None, "", "—"):
            return None
        return float(value)
    except Exception:
        return None

def _select_symbol_metadata(symbol_meta, side, sl, tp):
    if not isinstance(symbol_meta, dict):
        return {}

    meta_direction = str(symbol_meta.get("direction") or "").upper()
    if meta_direction and meta_direction != side.upper():
        return {}

    meta_sl = _to_float_or_none(symbol_meta.get("stop_loss"))
    meta_tp = _to_float_or_none(symbol_meta.get("take_profit"))
    live_sl = _to_float_or_none(sl)
    live_tp = _to_float_or_none(tp)

    if meta_sl is not None and live_sl is not None and abs(meta_sl - live_sl) > 0.01:
        return {}
    if meta_tp is not None and live_tp is not None and abs(meta_tp - live_tp) > 0.01:
        return {}

    return symbol_meta

def _get(path):
    r = requests.get(f"{BASE}{path}", headers=HDR, timeout=10)
    r.raise_for_status()
    return r.json()

def main():
    by_trade_id, by_order_id, by_symbol = _load_trade_opened_metadata()

    acc    = _get(f"/v3/accounts/{ACCOUNT_ID}/summary").get("account", {})
    bal    = float(acc.get("balance",    0))
    nav    = float(acc.get("NAV",        bal))
    margin = float(acc.get("marginUsed", 0))
    unreal = float(acc.get("unrealizedPL", 0))
    print(f"\n{'═'*66}")
    print(f"  Balance : ${bal:>10,.2f}    NAV: ${nav:>10,.2f}")
    print(f"  Margin  : ${margin:>10,.2f}  ({margin/nav*100:.1f}%)   UnrealPL: ${unreal:>+8,.2f}")
    print(f"{'═'*66}")

    trades = _get(f"/v3/accounts/{ACCOUNT_ID}/openTrades").get("trades", [])
    if not trades:
        print("  No open trades.\n")
        return

    syms   = ",".join({t["instrument"] for t in trades})
    prices = {p["instrument"]: p for p in
              _get(f"/v3/accounts/{ACCOUNT_ID}/pricing?instruments={syms}").get("prices", [])}

    print(f"  {'SYMBOL':10} {'DIR':4} {'ENTRY':>9} {'CURRENT':>9} {'PIPS':>6} {'P&L $':>9}  SL / TP")
    print(f"  {'-'*64}")
    for t in trades:
        sym   = t["instrument"]
        trade_id = str(t.get("id") or t.get("tradeID") or t.get("trade_id") or "")
        units = float(t["currentUnits"])
        side  = "BUY" if units > 0 else "SELL"
        entry = float(t["price"])
        pnl   = float(t.get("unrealizedPL", 0))
        px    = prices.get(sym, {})
        try:
            key = "asks" if side == "BUY" else "bids"
            cur = float(px[key][0]["price"])
        except Exception:
            cur = entry
        pip  = 0.01 if "JPY" in sym else 0.0001
        pips = (cur - entry) / pip if side == "BUY" else (entry - cur) / pip
        sl   = (t.get("stopLossOrder")   or {}).get("price", "—")
        tp   = (t.get("takeProfitOrder") or {}).get("price", "—")
        print(f"  {sym:10} {side:4} {entry:>9.5f} {cur:>9.5f} {pips:>+6.1f} {pnl:>+9.2f}  SL={sl} TP={tp}")

        meta = (
            by_trade_id.get(trade_id)
            or by_order_id.get(trade_id)
            or _select_symbol_metadata(by_symbol.get(sym.upper()) or {}, side, sl, tp)
            or {}
        )
        conf = _fmt_unknown(meta.get("signal_confidence"))
        votes = _fmt_unknown(meta.get("signal_votes"))
        detectors = meta.get("signal_detectors")
        if isinstance(detectors, (list, tuple, set)):
            strat = ",".join(str(x) for x in detectors if str(x).strip()) or "unknown"
        else:
            strat = _fmt_unknown(detectors)
        tf = _fmt_unknown(meta.get("signal_timeframe"))
        session = _fmt_unknown(meta.get("signal_session") or meta.get("session"))
        mgmt = _fmt_unknown(meta.get("management_profile"))
        
        # Determine if trailing is active from engine state or metadata heuristics
        # Note: in real-time we'd query the engine, but we rely on metadata/profile context here
        is_trailing = False
        # If it's a winning trade and has trail parameters
        if pnl > 0 and "trail" in str(mgmt).lower() and ("2R->trail" in str(mgmt) and pips > 15):
             is_trailing = True
             
        trail_badge = "\033[92m[ ✅ TRAILING ACTIVE ]\033[0m" if is_trailing else ""

        print(f"    Signal: conf={conf}, votes={votes}, strat={strat}, tf={tf}, session={session}")
        print(f"    Mgmt : {mgmt} {trail_badge}")
    print(f"{'═'*66}\n")

if __name__ == "__main__":
    main()
