"""
INTEGRATED PORTFOLIO ORCHESTRATOR
Ties together all aggressive portfolio management systems:
- Universal Position Registry
- Aggressive Portfolio Monitor
- Margin Maximizer
- LLM Command Interface
- Cross-Repo Coordinator

This is the ONE PLACE to start professional hedge fund style trading
with aggressive margin use, unified position tracking, and real-time monitoring.
"""

import asyncio
import time
from typing import Dict, Optional, List
from pathlib import Path

from util.universal_position_registry import get_registry, PositionSource
from util.aggressive_portfolio_monitor import AggressivePortfolioMonitor
from util.margin_maximizer import MarginMaximizer, create_margin_maximizer_config
from util.llm_command_interface import get_llm_interface
from util.cross_repo_coordinator import create_coordinator_for_clones
from util.oco_order_manager import get_oco_manager
from util.capital_pruning_engine import get_capital_pruning_engine
from util.net_positive_capital_engine import get_net_positive_capital_engine

class PortfolioOrchestrator:
    """
    Master orchestrator for aggressive, professional portfolio management.
    
    This system:
    1. Tracks ALL positions (autonomous + manual LLM)
    2. Monitors them aggressively (5-second checks)
    3. Exits immediately when going red
    4. Uses 5-10% margin per symbol (not 1.5%)
    5. Coordinates across cloned repos
    6. Allows LLM to open positions manually
    """
    
    def __init__(
        self,
        master_repo_path: str = "/home/rfing/RBOTZILLA_PHOENIX",
        account_balance: float = 25000.0,
        oanda_connector = None,
    ):
        print("\n" + "="*100)
        print("🏢 INITIALIZING PORTFOLIO ORCHESTRATOR - Professional Hedge Fund Trading")
        print("="*100 + "\n")
        
        self.master_repo_path = master_repo_path
        self.account_balance = account_balance
        self.oanda_connector = oanda_connector
        
        # Initialize all subsystems
        self.registry = get_registry()
        self.monitor = AggressivePortfolioMonitor(oanda_connector=self.oanda_connector, check_interval=5)
        self.margin_maximizer = MarginMaximizer(
            create_margin_maximizer_config(account_balance)
        )
        self.llm_interface = get_llm_interface()
        self.repo_coordinator = create_coordinator_for_clones(master_repo_path)
        
        # NET POSITIVE CAPITAL SYSTEMS
        self.oco_manager = get_oco_manager()
        self.pruning_engine = get_capital_pruning_engine()
        self.capital_engine = get_net_positive_capital_engine()
        
        self.is_operational = False
        
        print("✅ All subsystems initialized:")
        print("  ✅ Universal Position Registry")
        print("  ✅ Aggressive Portfolio Monitor (5-second checks)")
        print("  ✅ Margin Maximizer (5-10% sizing)")
        print("  ✅ LLM Command Interface (manual trading)")
        print("  ✅ Cross-Repo Coordinator")
        print("  ✅ OCO Order Manager (hardened exits)")
        print("  ✅ Capital Pruning Engine (remove losers)")
        print("  ✅ Net Positive Capital Engine (keep capital moving)")
        print()
    
    def start_trading(self, use_repo_sync: bool = True):
        """Start professional trading operations"""
        print("\n" + "="*100)
        print("🚀 STARTING PROFESSIONAL TRADING OPERATIONS")
        print("="*100 + "\n")
        
        # 1. Start aggressive portfolio monitor (5-second checks)
        self.monitor.start()
        
        # 2. Start net positive capital engine (OCO verification, pruning, reallocation)
        self.capital_engine.start_operations()
        
        # 3. Start cross-repo sync if enabled
        if use_repo_sync:
            self.repo_coordinator.start_sync_loop(interval=10)
        
        # 4. Display configuration
        self.print_operating_configuration()
        
        self.is_operational = True
        
        print("✅ Professional trading operations ACTIVE")
        print("\n⚡ CAPITAL PRESERVATION ACTIVE:")
        print("   • OCO orders verified every 30 seconds (hardened exits)")
        print("   • Red positions closed every 5 seconds (prevent big losses)")
        print("   • Stagnant positions pruned every 60 seconds (free capital)")
        print("   • Capital reallocated FROM losers TO winners continuously")
        print("   • Portfolio status reported every 5 minutes")
        print("\n💪 YOUR CAPITAL WORKS 24/7 TOWARD NET POSITIVE P&L")
        print()
    
    def stop_trading(self):
        """Stop trading operations"""
        print("\n⏹️  Stopping professional trading operations...")
        
        self.monitor.stop()
        self.capital_engine.stop_operations()
        self.repo_coordinator.stop_sync_loop()
        
        # Print final position summary
        print("\nFinal Position Summary:")
        self._print_portfolio_summary()
        
        self.is_operational = False
        print("✅ Operations stopped")
    
    def open_manual_position(
        self,
        symbol: str,
        direction: str,  # 'BUY' or 'SELL'
        entry_price: float,
        size_units: float,
        stop_loss: float,
        take_profit: float,
        reasoning: str = "",
    ) -> str:
        """
        Open a position via LLM command (manual trading)
        All manual positions tracked in universal registry
        """
        if direction.upper() == 'BUY':
            position_id = self.llm_interface.execute_buy_command(
                symbol=symbol,
                entry_price=entry_price,
                size_units=size_units,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=reasoning,
            )
        elif direction.upper() == 'SELL':
            position_id = self.llm_interface.execute_sell_command(
                symbol=symbol,
                entry_price=entry_price,
                size_units=size_units,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=reasoning,
            )
        else:
            print(f"❌ Invalid direction: {direction}")
            return ""
        
        # Broadcast to clones
        if position_id:
            self.repo_coordinator.broadcast_critical_update(
                'NEW_POSITION',
                {
                    'position_id': position_id,
                    'symbol': symbol,
                    'direction': direction,
                    'entry_price': entry_price,
                }
            )
        
        return position_id
    
    def close_manual_position(self, position_id: str):
        """Close a manual position"""
        position = self.registry.get_position_by_id(position_id)
        if not position:
            print(f"❌ Position not found: {position_id}")
            return False
        
        success = self.llm_interface.execute_close_command(
            position_id,
            "Manual close via LLM command"
        )
        
        if success:
            self.repo_coordinator.broadcast_critical_update(
                'POSITION_CLOSED',
                {
                    'position_id': position_id,
                    'symbol': position.symbol,
                }
            )
        
        return success
    
    def enable_auto_management(self, position_id: str):
        """Hand over a manual position to auto-management"""
        success = self.llm_interface.enable_auto_management(position_id)
        
        if success:
            self.repo_coordinator.broadcast_critical_update(
                'AUTO_MANAGEMENT_ENABLED',
                {'position_id': position_id}
            )
        
        return success
    
    def get_recommended_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_pips: float,
    ) -> float:
        """
        Get recommended position size using margin maximizer
        based on account balance and margin rules
        """
        return self.margin_maximizer.calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_pips=stop_loss_pips,
            account_balance=self.account_balance,
        )
    
    def create_hardened_oco(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> bool:
        """Create hardened OCO (One-Cancels-Other) order"""
        success, oco = self.oco_manager.create_oco_order(
            position_id=position_id,
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
        )
        return success
    
    def verify_all_oco_orders(self, recreate_broken: bool = True) -> Dict:
        """Verify all OCO orders are working"""
        return self.oco_manager.verify_all_oco_orders(recreate_broken=recreate_broken)
    
    def analyze_capital_pruning(self):
        """Analyze positions that should be pruned"""
        self.pruning_engine.print_pruning_report()
    
    def execute_capital_pruning(self) -> Dict:
        """Execute capital pruning (close red/stagnant positions)"""
        return self.pruning_engine.prune_portfolio(execute=True)
    
    def get_capital_efficiency_report(self) -> Dict:
        """Get how efficiently capital is being deployed"""
        return self.capital_engine.get_capital_efficiency()
    
    def print_operating_configuration(self):
        """Display current operating configuration"""
        print("📋 OPERATING CONFIGURATION")
        print("-" * 100)
        print(f"Account Balance: ${self.account_balance:,.2f}")
        print(f"Master Repository: {self.master_repo_path}")
        print(f"\n🎯 MARGIN & POSITION SIZING:")
        print(f"  Risk Per Trade: {(self.margin_maximizer.config.risk_per_trade_target*100):.1f}% of account")
        print(f"  Max Position per Symbol: {(self.margin_maximizer.config.max_position_size_percent*100):.0f}% of account")
        print(f"  Min Position Size: ${self.margin_maximizer.config.min_position_size_usd:,.2f}")
        print(f"\n🚨 RED ALERT SETTINGS:")
        print(f"  Exit Immediately If Loss > {(self.monitor.RED_ALERT_LOSS_PERCENT*100):.1f}%")
        print(f"  Monitor Interval: {self.monitor.check_interval} seconds")
        print(f"\n🔄 CROSS-REPO SYNC:")
        print(f"  Master Repo: {self.master_repo_path}")
        print(f"  Slave Repos: {self.repo_coordinator.repo_coordinator.slave_repo_paths if hasattr(self.repo_coordinator, 'repo_coordinator') else 'None found'}")
        print(f"  Sync Interval: {self.repo_coordinator.sync_interval} seconds")
        print(f"\n📊 POSITION TRACKING:")
        print(f"  Universal Registry: ALL positions (autonomous + manual)")
        print(f"  Auto-Close on Hit TP/SL: Yes")
        print(f"  Manual Position Support: Yes (via LLM)")
        print("-" * 100 + "\n")
    
    def print_full_status_report(self):
        """Print comprehensive status report"""
        print("\n" + "="*100)
        print("PROFESSIONAL PORTFOLIO STATUS REPORT")
        print("="*100 + "\n")
        
        # Portfolio summary
        print("📊 PORTFOLIO STATE:")
        print("-" * 100)
        summary = self.registry.get_portfolio_summary()
        print(f"  Open Positions: {summary['total_open_positions']}")
        print(f"    - Autonomous: {summary['autonomous_positions']}")
        print(f"    - Manual (LLM): {summary['manual_positions']}")
        print(f"  Total Notional: ${summary['total_notional']:,.2f}")
        print(f"  Total P&L: ${summary['total_pnl_usd']:+.2f}")
        print(f"  Average Return: {summary['avg_pnl_percent']:+.2f}%")
        print(f"  Positions in Green: {summary['positions_in_green']}")
        print(f"  Positions in Red: {summary['positions_in_red']}")
        
        # Capital efficiency
        print("\n💪 CAPITAL EFFICIENCY:")
        print("-" * 100)
        efficiency = self.get_capital_efficiency_report()
        print(f"  Efficiency Score: {efficiency['efficiency_score']:.1f}/100")
        print(f"  Notional Deployed: ${efficiency['notional_deployed']:,.2f}")
        print(f"  P&L per Notional: {efficiency['pnl_per_notional']:.2f}%")
        print(f"  Average Position Return: {efficiency['avg_position_return']:+.2f}%")
        
        # OCO status
        print("\n🔐 OCO ORDER PROTECTION:")
        print("-" * 100)
        self.oco_manager.print_oco_status()
        
        # Capital preservation
        print("\n✂️  CAPITAL PRESERVATION:")
        print("-" * 100)
        self.pruning_engine.print_pruning_report()
        
        # Monitor status
        print("\n🚨 AGGRESSIVE MONITORING:")
        print("-" * 100)
        self.monitor.print_monitor_report()
        
        # Repo sync status
        print("\n🔄 CROSS-REPO SYNC:")
        print("-" * 100)
        self.repo_coordinator.print_sync_report()
        
        # Margin status
        print("\n💰 MARGIN & POSITION SIZING:")
        print("-" * 100)
        self.margin_maximizer.print_allocation_report(self.account_balance)
        
        # Manual positions
        print("\n👤 MANUAL POSITIONS (LLM Commands):")
        print("-" * 100)
        self.llm_interface.print_manual_positions_summary()
        
        print("="*100 + "\n")
    
    def _print_portfolio_summary(self):
        """Print quick portfolio summary"""
        summary = self.registry.get_portfolio_summary()
        print(f"  Open Positions: {summary['total_open_positions']}")
        print(f"  Total P&L: ${summary['total_pnl_usd']:+.2f}")
        print(f"  Total Notional: ${summary['total_notional']:,.2f}")


# Global instance
_orchestrator = None

def get_orchestrator(
    master_repo_path: str = "/home/rfing/RBOTZILLA_PHOENIX",
    account_balance: float = 25000.0,
) -> PortfolioOrchestrator:
    """Get or create global orchestrator"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PortfolioOrchestrator(master_repo_path, account_balance)
    return _orchestrator
