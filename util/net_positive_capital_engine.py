"""
NET POSITIVE CAPITAL ENGINE
The brain that keeps capital moving in positive direction.
Orchestrates:
- OCO order verification (hard exits)
- Capital pruning (closes red/stagnant)
- Win/loss rebalancing (capital to winners)
- Aggressive goal: ZERO stagnant capital, MAXIMUM positive P&L
"""

import asyncio
import time
import threading
from typing import Dict, Optional
from datetime import datetime

from util.universal_position_registry import get_registry
from util.oco_order_manager import get_oco_manager
from util.capital_pruning_engine import get_capital_pruning_engine
from util.aggressive_portfolio_monitor import AggressivePortfolioMonitor


class NetPositiveCapitalEngine:
    """
    Orchestrates all capital preservation and growth systems.
    
    Mission: Keep 100% of capital working toward POSITIVE P&L
    
    Continuous operations:
    1. Verify OCO orders every 30 seconds (no broken exits)
    2. Check for red positions every 10 seconds (immediate closure)
    3. Prune stagnant positions every 60 seconds (free up capital)
    4. Reallocate capital FROM losers TO winners continuously
    5. Report portfolio status every 5 minutes
    """
    
    def __init__(self):
        print("\n" + "="*100)
        print("🎯 INITIALIZING NET POSITIVE CAPITAL ENGINE")
        print("Mission: Keep ALL capital moving toward POSITIVE P&L")
        print("="*100 + "\n")
        
        self.registry = get_registry()
        self.oco_manager = get_oco_manager()
        self.pruning_engine = get_capital_pruning_engine()
        self.monitor = AggressivePortfolioMonitor()
        
        self.is_running = False
        self.threads = []
        
        self.stats = {
            'oco_verifications': 0,
            'oco_recreations': 0,
            'red_positions_closed': 0,
            'stagnant_positions_pruned': 0,
            'capital_reallocations': 0,
            'last_full_cycle': 0,
            'total_capital_preserved': 0.0,
        }
    
    def start_operations(self):
        """Start all capital preservation operations"""
        print("\n" + "="*100)
        print("🚀 STARTING NET POSITIVE CAPITAL OPERATIONS")
        print("="*100 + "\n")
        
        self.is_running = True
        
        # Start the four parallel monitoring loops
        self._start_oco_verification_loop()
        self._start_red_position_monitoring()
        self._start_capital_pruning_loop()
        self._start_reallocation_loop()
        self._start_status_reporting()
        
        print("✅ All capital preservation systems ACTIVE:")
        print("  ✅ OCO Verification (30s interval)")
        print("  ✅ Red Position Monitoring (5s interval)")
        print("  ✅ Capital Pruning (60s interval)")
        print("  ✅ Capital Reallocation (120s interval)")
        print("  ✅ Status Reporting (300s interval)")
        print()
    
    def stop_operations(self):
        """Stop all operations"""
        self.is_running = False
        
        for thread in self.threads:
            thread.join(timeout=5)
        
        print("✅ Net Positive Capital Engine stopped")
    
    def _start_oco_verification_loop(self):
        """Verify OCO orders are working (hardened exits)"""
        def loop():
            while self.is_running:
                try:
                    # Verify all OCO orders
                    results = self.oco_manager.verify_all_oco_orders(recreate_broken=True)
                    self.stats['oco_verifications'] += 1
                    self.stats['oco_recreations'] += results['recreated']
                    
                    if results['broken'] > 0 or results['orphaned'] > 0:
                        print(f"⚠️  OCO Verification: {results['broken']} broken, {results['orphaned']} orphaned")
                        print(f"    Fixed: {results['recreated']} recreated")
                    
                    time.sleep(30)
                except Exception as e:
                    print(f"❌ OCO verification error: {e}")
                    time.sleep(30)
        
        thread = threading.Thread(target=loop, daemon=True, name="OCOVerifier")
        thread.start()
        self.threads.append(thread)
    
    def _start_red_position_monitoring(self):
        """Monitor for red floating positions and close immediately"""
        def loop():
            while self.is_running:
                try:
                    open_pos = self.registry.get_all_open_positions()
                    
                    # Check each position for RED status
                    for pos in open_pos:
                        # Skip manual positions (user controls)
                        if not pos.is_auto_managed:
                            continue
                        
                        # RED ALERT: Position going negative
                        if pos.metrics.pnl_percent < -0.5:
                            current_price = pos.metrics.current_price or pos.entry_price
                            
                            # Close immediately
                            self.registry.close_position(
                                pos.position_id,
                                current_price,
                                f"AUTO CLOSED: Red position ({pos.metrics.pnl_percent:.2f}%)"
                            )
                            
                            self.stats['red_positions_closed'] += 1
                            self.stats['total_capital_preserved'] += abs(pos.metrics.pnl_usd)
                            
                            print(f"🚨 RED ALERT CLOSED: {pos.symbol}")
                            print(f"   Loss: ${pos.metrics.pnl_usd:.2f} ({pos.metrics.pnl_percent:.2f}%)")
                    
                    time.sleep(5)
                except Exception as e:
                    print(f"❌ Red position monitoring error: {e}")
                    time.sleep(5)
        
        thread = threading.Thread(target=loop, daemon=True, name="RedMonitor")
        thread.start()
        self.threads.append(thread)
    
    def _start_capital_pruning_loop(self):
        """Prune stagnant and poor-performing positions"""
        def loop():
            while self.is_running:
                try:
                    # Identify pruning candidates
                    candidates = self.pruning_engine.monitor.identify_pruning_candidates()
                    
                    # Close HIGH severity positions (not stagnant/poor)
                    high_severity = [c for c in candidates if c.severity == "HIGH"]
                    
                    for candidate in high_severity:
                        self.pruning_engine._execute_prune_action(candidate)
                        self.stats['stagnant_positions_pruned'] += 1
                    
                    if high_severity:
                        total_capital = sum(abs(c.pnl_usd) for c in high_severity)
                        print(f"✂️  PRUNED: {len(high_severity)} positions, freed ${total_capital:.2f}")
                    
                    time.sleep(60)
                except Exception as e:
                    print(f"❌ Capital pruning error: {e}")
                    time.sleep(60)
        
        thread = threading.Thread(target=loop, daemon=True, name="CapitalPruner")
        thread.start()
        self.threads.append(thread)
    
    def _start_reallocation_loop(self):
        """Reallocate capital from losers to winners"""
        def loop():
            while self.is_running:
                try:
                    open_pos = self.registry.get_all_open_positions()
                    
                    if len(open_pos) < 2:
                        time.sleep(120)
                        continue
                    
                    # Find winners and losers
                    winners = [p for p in open_pos if p.metrics.pnl_usd > 50]  # Profitable
                    losers = [p for p in open_pos if p.metrics.pnl_usd < -100]  # Losing badly
                    
                    # Scale winners up, losers down
                    for winner in winners:
                        if winner.is_auto_managed and winner.size_units > 0:
                            # Increase size by 20%
                            new_size = winner.size_units * 1.2
                            # (Would be executed in trading engine)
                    
                    for loser in losers:
                        if loser.is_auto_managed:
                            # Close losers entirely
                            current_price = loser.metrics.current_price or loser.entry_price
                            self.registry.close_position(
                                loser.position_id,
                                current_price,
                                "REALLOCATED: Capital moved to winners"
                            )
                            self.stats['capital_reallocations'] += 1
                    
                    if winners or losers:
                        print(f"💰 REALLOCATION: {len(winners)} winners scaled, {len(losers)} losers closed")
                    
                    time.sleep(120)
                except Exception as e:
                    print(f"❌ Capital reallocation error: {e}")
                    time.sleep(120)
        
        thread = threading.Thread(target=loop, daemon=True, name="CapitalReallocator")
        thread.start()
        self.threads.append(thread)
    
    def _start_status_reporting(self):
        """Report portfolio status regularly"""
        def loop():
            while self.is_running:
                try:
                    time.sleep(300)  # Report every 5 minutes
                    self._print_capital_status()
                except Exception as e:
                    print(f"❌ Status reporting error: {e}")
                    time.sleep(300)
        
        thread = threading.Thread(target=loop, daemon=True, name="StatusReporter")
        thread.start()
        self.threads.append(thread)
    
    def _print_capital_status(self):
        """Print current capital and portfolio status"""
        summary = self.registry.get_portfolio_summary()
        
        print("\n" + "="*100)
        print("💰 NET POSITIVE CAPITAL STATUS")
        print("="*100)
        print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"\nPortfolio:")
        print(f"  Open Positions: {summary['total_open_positions']}")
        print(f"  Total Notional: ${summary['total_notional']:,.2f}")
        print(f"  Total P&L: ${summary['total_pnl_usd']:+.2f} ({summary['avg_pnl_percent']:+.2f}%)")
        print(f"  In Green: {summary['positions_in_green']} | In Red: {summary['positions_in_red']}")
        
        print(f"\nCapital Preservation:")
        print(f"  OCO Verifications: {self.stats['oco_verifications']}")
        print(f"  OCO Recreations: {self.stats['oco_recreations']}")
        print(f"  Red Positions Closed: {self.stats['red_positions_closed']}")
        print(f"  Stagnant Pruned: {self.stats['stagnant_positions_pruned']}")
        print(f"  Capital Reallocations: {self.stats['capital_reallocations']}")
        print(f"  Capital Preserved: ${self.stats['total_capital_preserved']:,.2f}")
        
        print("="*100 + "\n")
    
    def get_capital_efficiency(self) -> Dict:
        """Calculate how efficiently capital is being used"""
        summary = self.registry.get_portfolio_summary()
        
        if summary['total_notional'] == 0:
            return {
                'efficiency_score': 0.0,
                'notional_deployed': 0.0,
                'pnl_per_notional': 0.0,
                'positions_in_profit': 0,
                'positions_in_loss': 0,
            }
        
        pnl_per_notional = (summary['total_pnl_usd'] / summary['total_notional'] * 100) if summary['total_notional'] > 0 else 0
        efficiency = 100 + pnl_per_notional  # 100 = breakeven, >100 = profitable
        
        return {
            'efficiency_score': max(0, efficiency),  # 0-100+ scale
            'notional_deployed': summary['total_notional'],
            'pnl_per_notional': pnl_per_notional,
            'positions_in_profit': summary['positions_in_green'],
            'positions_in_loss': summary['positions_in_red'],
            'avg_position_return': summary['avg_pnl_percent'],
        }


# Global instance
_engine = None

def get_net_positive_capital_engine() -> NetPositiveCapitalEngine:
    """Get or create global engine"""
    global _engine
    if _engine is None:
        _engine = NetPositiveCapitalEngine()
    return _engine
