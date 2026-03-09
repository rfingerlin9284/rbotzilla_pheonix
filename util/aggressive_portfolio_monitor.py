"""
AGGRESSIVE PORTFOLIO MONITOR
Checks ALL positions (autonomous + manual) every 5 seconds
Executes immediate exits on red-alert (trade going negative)
Coordinates across cloned repositories
Manages aggressive portfolio updates and rebalancing
"""

import asyncio
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import shutil

from util.universal_position_registry import (
    get_registry,
    PositionStatus,
    SLMode,
    PositionSource,
)

class AggressivePortfolioMonitor:
    """
    Real-time portfolio oversight:
    - Checks ALL positions every 5 seconds
    - Immediate exits on negative moves (RED ALERT)
    - Coordinates positions across repo clones
    - Updates all positions with live P&L
    - Aggressive rebalancing
    """
    
    def __init__(self, oanda_connector=None, check_interval: int = 5):
        self.registry = get_registry()
        self.oanda_connector = oanda_connector
        self.check_interval = check_interval  # seconds
        
        self.is_running = False
        self.monitor_thread = None
        
        self.stats = {
            'checks_performed': 0,
            'red_alerts_triggered': 0,
            'positions_closed': 0,
            'sl_adjustments': 0,
            'last_check': 0,
            'total_money_saved_red_alert': 0.0,
        }
        
        # Thresholds for RED ALERT
        self.RED_ALERT_LOSS_PERCENT = -0.2  # Close if -0.2% or worse immediately
        self.RED_ALERT_MOMENTUM_BREAK = 0.4  # If momentum <0.4 and losing
        
    def start(self):
        """Start the aggressive monitor in background"""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="AggressivePortfolioMonitor"
        )
        self.monitor_thread.start()
        print(f"🚀 Aggressive Portfolio Monitor started (check every {self.check_interval}s)")
    
    def stop(self):
        """Stop the monitor"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("⏹️  Portfolio Monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                self._check_all_positions()
                time.sleep(self.check_interval)
            except Exception as e:
                print(f"⚠️  Monitor error: {e}")
                time.sleep(self.check_interval)
    
    def _check_all_positions(self):
        """Check every open position for updates and red alerts"""
        self.stats['checks_performed'] += 1
        self.stats['last_check'] = time.time()
        
        open_positions = self.registry.get_all_open_positions()
        
        if not open_positions:
            return
        
        for position in open_positions:
            self._check_position(position)
    
    def _check_position(self, position):
        """Check a single position for updates and exit conditions"""
        
        # Get current market price (if we have connector)
        current_price = self._get_current_price(position.symbol)
        if not current_price:
            return
        
        # Calculate current P&L
        pnl_usd = (current_price - position.entry_price) * position.size_units
        direction_multiplier = 1.0 if position.size_units > 0 else -1.0
        pnl_percent = (((current_price - position.entry_price) * direction_multiplier) / position.entry_price) * 100
        
        # Update metrics
        self.registry.update_position_metrics(
            position.position_id,
            current_price=current_price,
            pnl_usd=pnl_usd,
            pnl_percent=pnl_percent,
        )
        
        # Check for exit conditions
        
        # 1. Check if hit take profit
        if self._check_tp_hit(position, current_price):
            return  # Position will be closed by TP logic
        
        # 2. Check if hit stop loss
        if self._check_sl_hit(position, current_price):
            return  # Position will be closed by SL logic
        
        # 3. RED ALERT: Trade going negative - exit IMMEDIATELY
        if pnl_percent < self.RED_ALERT_LOSS_PERCENT and position.is_auto_managed:
            self._execute_red_alert(position, current_price, pnl_percent)
            self.stats['red_alerts_triggered'] += 1
            self.stats['total_money_saved_red_alert'] += abs(pnl_usd)
            return
        
        # 4. Adjust SL based on momentum (if available from system)
        if position.is_auto_managed:
            self._consider_aggressive_sl_adjustment(position, current_price, pnl_percent)
        
        # 5. Print real-time update every 30 seconds
        if int(time.time()) % 30 == 0:
            self._print_position_status(position)
    
    def _check_tp_hit(self, position, current_price: float) -> bool:
        """Check if position hit take profit"""
        if position.source == PositionSource.MANUAL_PROMPT:
            # Manual positions: only close at TP if explicitly 3:1 R:R minimum
            tp_hit = (
                (position.take_profit > position.entry_price and current_price >= position.take_profit) or
                (position.take_profit < position.entry_price and current_price <= position.take_profit)
            )
        else:
            # Auto positions: standard TP check
            tp_hit = (
                (position.take_profit > position.entry_price and current_price >= position.take_profit) or
                (position.take_profit < position.entry_price and current_price <= position.take_profit)
            )
        
        if tp_hit:
            pnl_usd = (current_price - position.entry_price) * position.size_units
            self.registry.close_position(
                position.position_id,
                current_price,
                f"TP_HIT (${pnl_usd:.2f} profit)"
            )
            self.stats['positions_closed'] += 1
            return True
        
        return False
    
    def _check_sl_hit(self, position, current_price: float) -> bool:
        """Check if position hit stop loss"""
        sl_hit = (
            (position.current_sl > position.entry_price and current_price <= position.current_sl) or
            (position.current_sl < position.entry_price and current_price >= position.current_sl)
        )
        
        if sl_hit:
            pnl_usd = (current_price - position.entry_price) * position.size_units
            self.registry.close_position(
                position.position_id,
                current_price,
                f"SL_HIT (${pnl_usd:.2f} loss)"
            )
            self.stats['positions_closed'] += 1
            return True
        
        return False
    
    def _execute_red_alert(self, position, current_price: float, pnl_percent: float):
        """
        🚨 RED ALERT: Trade is going negative - EXIT IMMEDIATELY
        This is aggressive loss prevention
        """
        pnl_usd = (current_price - position.entry_price) * position.size_units
        
        print(f"🚨 RED ALERT TRIGGERED: {position.symbol} {position.position_id}")
        print(f"   Entry: {position.entry_price} → Current: {current_price}")
        print(f"   P&L: ${pnl_usd:.2f} ({pnl_percent:.2f}%)")
        print(f"   CLOSING POSITION IMMEDIATELY")
        
        # Force immediate closure on broker side
        from util.oco_order_manager import get_oco_manager
        oco_mgr = get_oco_manager()
        if oco_mgr and oco_mgr.oanda_connector:
            try:
                oco_mgr.oanda_connector.close_trade(position.position_id)
                print(f"✅ Broker executing immediate close for RED ALERT")
            except Exception as e:
                print(f"⚠️  Broker close failed for RED ALERT: {e}")
        
        # Move SL to current price (force immediate exit) locally
        self.registry.move_stop_loss(
            position.position_id,
            current_price,
            SLMode.RED_ALERT,
            f"RED ALERT: Immediate exit at {pnl_percent:.2f}% loss"
        )
        
        # Actually close the position
        self.registry.close_position(
            position.position_id,
            current_price,
            f"RED_ALERT (${pnl_usd:.2f} loss, {pnl_percent:.2f}%)"
        )
        
        self.stats['positions_closed'] += 1
    
    def _consider_aggressive_sl_adjustment(self, position, current_price: float, pnl_percent: float):
        """Adjust SL aggressively to protect profits"""
        
        is_long = position.size_units > 0
        
        # If position is profitable, move SL to breakeven or above
        if pnl_percent > 0.5:  # 0.5% profit
            if is_long:
                new_sl = max(position.current_sl, position.entry_price + 0.0001)
                sl_improved = new_sl > position.current_sl
            else:
                new_sl = min(position.current_sl, position.entry_price - 0.0001)
                sl_improved = new_sl < position.current_sl
            
            if sl_improved:
                self.registry.move_stop_loss(
                    position.position_id,
                    new_sl,
                    SLMode.BREAKEVEN,
                    f"Profit protection: Moving SL {'higher' if is_long else 'lower'}"
                )
                from util.oco_order_manager import get_oco_manager
                get_oco_manager().update_stop_loss_order(position.position_id, new_sl)
                self.stats['sl_adjustments'] += 1
        
        # If position has bigger profit, trail more aggressively
        if pnl_percent > 1.0:  # 1% profit
            atr = self._estimate_atr(position.symbol)
            if is_long:
                aggressive_trail = current_price - (1.0 * atr)  # Trail 1x ATR below current price
                sl_improved = aggressive_trail > position.current_sl
            else:
                aggressive_trail = current_price + (1.0 * atr)  # Trail 1x ATR above current price
                sl_improved = aggressive_trail < position.current_sl
            
            if sl_improved:
                self.registry.move_stop_loss(
                    position.position_id,
                    aggressive_trail,
                    SLMode.MOMENTUM_TRAIL,
                    f"Aggressive trail: 1x ATR ({atr:.5f})"
                )
                from util.oco_order_manager import get_oco_manager
                get_oco_manager().update_stop_loss_order(position.position_id, aggressive_trail)
                self.stats['sl_adjustments'] += 1
    
    def _print_position_status(self, position):
        """Print readable status of a position"""
        duration = int(time.time() - position.entry_time)
        pnl = position.metrics.pnl_usd
        pnl_pct = position.metrics.pnl_percent
        
        color = "🟢" if pnl > 0 else "🔴"
        
        print(
            f"{color} {position.symbol} | "
            f"Entry: {position.entry_price:.5f} → Now: {position.metrics.current_price:.5f} | "
            f"P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%) | "
            f"SL: {position.current_sl:.5f} | "
            f"TP: {position.take_profit:.5f} | "
            f"Age: {duration}s"
        )
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price for a symbol"""
        if self.oanda_connector:
            try:
                # Fetch real-time price snapshot
                prices = self.oanda_connector.get_live_prices([symbol])
                if prices and symbol in prices:
                    p = prices[symbol]
                    if p.get('mid') is not None:
                        return p['mid']
                    elif p.get('bid') is not None and p.get('ask') is not None:
                        return (p['bid'] + p['ask']) / 2.0
            except Exception as e:
                print(f"⚠️  Failed to get price for {symbol}: {e}")
        return None
    
    def _estimate_atr(self, symbol: str) -> float:
        """Estimate ATR (Average True Range) for position sizing"""
        # Simplified: return a default based on volatility
        # Real implementation would calculate from candles
        return 0.0010  # 10 pips as default
    
    def sync_with_repo_clone(self, clone_repo_path: str):
        """
        Sync positions with a cloned repository.
        Read their portfolio snapshot, merge into ours.
        """
        portfolio_file = Path(clone_repo_path) / "portfolio_registry" / "portfolio_snapshot_latest.json"
        
        if portfolio_file.exists():
            try:
                self.registry.import_portfolio_json(str(portfolio_file))
                print(f"✅ Synced positions from {clone_repo_path}")
            except Exception as e:
                print(f"⚠️  Failed to sync {clone_repo_path}: {e}")
        else:
            print(f"⚠️  No portfolio snapshot found at {clone_repo_path}")
    
    def broadcast_portfolio_state(self, clone_paths: List[str]):
        """Export our portfolio snapshot to clone repositories"""
        snapshot_file = self.registry.export_portfolio_json()
        
        for clone_path in clone_paths:
            try:
                clone_reg_dir = Path(clone_path) / "portfolio_registry"
                clone_reg_dir.mkdir(exist_ok=True)
                
                # Copy our snapshot to their directory
                shutil.copy(snapshot_file, clone_reg_dir / "portfolio_snapshot_latest.json")
                print(f"📤 Broadcast portfolio to {clone_path}")
            except Exception as e:
                print(f"⚠️  Failed to broadcast to {clone_path}: {e}")
    
    def get_monitor_status(self) -> Dict:
        """Get monitor status and statistics"""
        return {
            'is_running': self.is_running,
            'checks_performed': self.stats['checks_performed'],
            'red_alerts_triggered': self.stats['red_alerts_triggered'],
            'positions_closed': self.stats['positions_closed'],
            'sl_adjustments': self.stats['sl_adjustments'],
            'total_money_saved_red_alert': self.stats['total_money_saved_red_alert'],
            'last_check': datetime.fromtimestamp(self.stats['last_check']),
            'open_positions': len(self.registry.get_all_open_positions()),
            'portfolio_summary': self.registry.get_portfolio_summary(),
        }
    
    def print_monitor_report(self):
        """Print detailed monitor status report"""
        status = self.get_monitor_status()
        
        print("\n" + "=" * 80)
        print("AGGRESSIVE PORTFOLIO MONITOR REPORT")
        print("=" * 80)
        print(f"Status: {'🟢 RUNNING' if status['is_running'] else '🔴 STOPPED'}")
        print(f"Last Check: {status['last_check']}")
        print(f"\nStatistics:")
        print(f"  Checks Performed: {status['checks_performed']}")
        print(f"  Red Alerts Triggered: {status['red_alerts_triggered']}")
        print(f"  Positions Closed: {status['positions_closed']}")
        print(f"  SL Adjustments: {status['sl_adjustments']}")
        print(f"  💰 Money Saved (Red Alert): ${status['total_money_saved_red_alert']:.2f}")
        print(f"\nPortfolio:")
        summary = status['portfolio_summary']
        print(f"  Open Positions: {summary['total_open_positions']}")
        print(f"    - Autonomous: {summary['autonomous_positions']}")
        print(f"    - Manual: {summary['manual_positions']}")
        print(f"  Total Notional: ${summary['total_notional']:.2f}")
        print(f"  Total P&L: ${summary['total_pnl_usd']:.2f} ({summary['avg_pnl_percent']:.2f}%)")
        print(f"  In Green: {summary['positions_in_green']} | In Red: {summary['positions_in_red']}")
        print("=" * 80 + "\n")
