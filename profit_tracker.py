#!/usr/bin/env python3
"""
Daily Profit Tracker for $200-500 Target
Monitors live P&L and compares against goal
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
TRACKING_FILE = LOG_DIR / "daily_profit_tracking.jsonl"

def log_trade_result(symbol: str, direction: str, entry: float, exit_price: float, 
                     units: float, notional_usd: float, pnl_usd: float, pnl_pct: float):
    """Log individual trade result"""
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "exit": exit_price,
        "units": units,
        "notional_usd": notional_usd,
        "pnl_usd": round(pnl_usd, 2),
        "pnl_pct": round(pnl_pct, 4),
        "status": "WIN" if pnl_usd > 0 else "LOSS",
    }
    
    with open(TRACKING_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
    
    return record

def get_daily_summary(date_str: str = None) -> dict:
    """Get summary for a specific date (YYYY-MM-DD or 'today')"""
    if date_str is None or date_str.lower() == "today":
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    if not TRACKING_FILE.exists():
        return {
            "date": date_str,
            "trades": [],
            "total_pnl_usd": 0,
            "total_pnl_pct": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0,
            "target_met": False,
        }
    
    trades = []
    with open(TRACKING_FILE, "r") as f:
        for line in f:
            try:
                record = json.loads(line)
                rec_date = record["timestamp"].split("T")[0]
                if rec_date == date_str:
                    trades.append(record)
            except:
                pass
    
    total_pnl = sum(t["pnl_usd"] for t in trades)
    wins = len([t for t in trades if t["status"] == "WIN"])
    losses = len([t for t in trades if t["status"] == "LOSS"])
    win_rate = (wins / len(trades) * 100) if trades else 0
    
    return {
        "date": date_str,
        "trades": trades,
        "total_pnl_usd": round(total_pnl, 2),
        "total_pnl_pct": round(sum(t["pnl_pct"] for t in trades), 4),
        "win_count": wins,
        "loss_count": losses,
        "win_rate": round(win_rate, 1),
        "target_met": total_pnl >= 200,
        "target_range": "✅ TARGET MET" if total_pnl >= 200 else f"⚠️  ${total_pnl:.0f} (need ${200-total_pnl:.0f} more)",
    }

def print_daily_report():
    """Print today's summary"""
    summary = get_daily_summary("today")
    
    print("\n" + "="*80)
    print("📊 DAILY PROFIT TRACKING - " + summary["date"])
    print("="*80)
    
    if not summary["trades"]:
        print("No trades recorded yet today.")
        print("\nTarget: $200-500 daily profit")
        print("Status: Waiting for trades...")
        return
    
    print(f"\n📈 P&L Summary:")
    print(f"   Total P&L:     ${summary['total_pnl_usd']:>8.2f}")
    print(f"   Total Return:  {summary['total_pnl_pct']:>8.2%}")
    print(f"   Trade Count:   {len(summary['trades']):>8} trades")
    print(f"   Win Rate:      {summary['win_rate']:>8.1f}% ({summary['win_count']} wins, {summary['loss_count']} losses)")
    print(f"\n🎯 Daily Target:")
    print(f"   Target Range:  $200 - $500")
    print(f"   Status:        {summary['target_range']}")
    
    print(f"\n📋 Recent Trades (Last 5):")
    print(f"   {'Time':<20} {'Symbol':<10} {'Dir':<5} {'PnL':<10} {'%':<8} {'Status':<6}")
    print("   " + "-"*65)
    
    for trade in summary["trades"][-5:]:
        time_str = trade["timestamp"].split("T")[1][:8]
        pnl_str = f"${trade['pnl_usd']:>7.2f}"
        pct_str = f"{trade['pnl_pct']:>6.2%}"
        status = "✅" if trade['status'] == "WIN" else "❌"
        print(f"   {time_str:<20} {trade['symbol']:<10} {trade['direction']:<5} {pnl_str:<10} {pct_str:<8} {status}")
    
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "report":
            date = sys.argv[2] if len(sys.argv) > 2 else None
            summary = get_daily_summary(date)
            print(json.dumps(summary, indent=2))
        elif sys.argv[1] == "today":
            print_daily_report()
    else:
        print_daily_report()
