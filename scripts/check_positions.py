#!/usr/bin/env python3
"""scripts/check_positions.py — OANDA position snapshot"""
import os, sys, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Load creds from root .env (where the real values live)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

TOKEN      = os.getenv("OANDA_PRACTICE_TOKEN") or os.getenv("OANDA_API_KEY", "")
ACCOUNT_ID = os.getenv("OANDA_PRACTICE_ACCOUNT_ID") or os.getenv("OANDA_ACCOUNT_ID", "")
BASE       = "https://api-fxpractice.oanda.com"
HDR        = {"Authorization": f"Bearer {TOKEN}"}

def _get(path):
    r = requests.get(f"{BASE}{path}", headers=HDR, timeout=10)
    r.raise_for_status()
    return r.json()

def main():
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

    print(f"  {'SYMBOL':10} {'DIR':4} {'ENTRY':>9} {'CURRENT':>9} {'PIPS':>+6} {'P&L $':>9}  SL / TP")
    print(f"  {'-'*64}")
    for t in trades:
        sym   = t["instrument"]
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
    print(f"{'═'*66}\n")

if __name__ == "__main__":
    main()
