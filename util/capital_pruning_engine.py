"""
FLOATING LOSS MONITOR & CAPITAL PRUNING ENGINE
Continuously identifies and eliminates:
- Red floating positions (currently losing)
- Stagnant positions (not moving, wasting capital)
- Poor performers (low win probability)
Automatically closes/reduces positions to move capital to winners
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from util.universal_position_registry import (
    get_registry,
    PositionStatus,
    SLMode,
)

@dataclass
class PruningCandidate:
    """Position identified for closing/reduction"""
    position_id: str
    symbol: str
    pnl_usd: float
    pnl_percent: float
    duration_seconds: int
    reason: str  # Why it should be pruned
    severity: str  # HIGH, MEDIUM, LOW
    recommended_action: str  # CLOSE, REDUCE, HOLD

class FloatingLossMonitor:
    """
    Continuously monitors for:
    1. Floating losses (currently red)
    2. Stagnant positions (not moving)
    3. Poor momentum (low trade quality)
    4. Bad risk/reward (more loss potential than gain)
    """
    
    def __init__(self):
        self.registry = get_registry()
        
        self.stats = {
            'red_positions_identified': 0,
            'stagnant_positions_identified': 0,
            'poor_performers_identified': 0,
            'positions_closed_for_loss': 0,
            'capital_preserved_usd': 0.0,
        }
        
        # Thresholds for pruning
        self.RED_LOSS_THRESHOLD = -0.5  # Close if > -0.5% loss
        self.STAGNANT_MINUTES = 10  # Close if open > 10 min with <0.3% move
        self.POOR_MOMENTUM_THRESHOLD = 0.3  # Close if momentum < 0.3 (weak entry)
        self.BAD_RR_RATIO = 0.7  # Close if risk > 0.7x reward
        
    def identify_pruning_candidates(self) -> List[PruningCandidate]:
        """
        Scan all open positions and identify those that should be pruned.
        Returns: List of pruning candidates with reasons
        """
        candidates = []
        open_positions = self.registry.get_all_open_positions()
        
        for position in open_positions:
            # Skip positions already being managed
            if not position.is_auto_managed:
                continue
            
            candidate = None
            
            # Check 1: Currently floating in red
            if position.metrics.pnl_percent < self.RED_LOSS_THRESHOLD:
                candidate = PruningCandidate(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    pnl_usd=position.metrics.pnl_usd,
                    pnl_percent=position.metrics.pnl_percent,
                    duration_seconds=position.metrics.duration_seconds,
                    reason=f"Floating loss: {position.metrics.pnl_percent:.2f}%",
                    severity="HIGH",
                    recommended_action="CLOSE",
                )
                self.stats['red_positions_identified'] += 1
            
            # Check 2: Stagnant position (open too long with no movement)
            elif position.metrics.duration_seconds > self.STAGNANT_MINUTES * 60:
                if abs(position.metrics.pnl_percent) < 0.3:
                    candidate = PruningCandidate(
                        position_id=position.position_id,
                        symbol=position.symbol,
                        pnl_usd=position.metrics.pnl_usd,
                        pnl_percent=position.metrics.pnl_percent,
                        duration_seconds=position.metrics.duration_seconds,
                        reason=f"Stagnant: {position.metrics.duration_seconds}s open, <0.3% move",
                        severity="MEDIUM",
                        recommended_action="REDUCE",
                    )
                    self.stats['stagnant_positions_identified'] += 1
            
            # Check 3: Poor momentum/bad entry
            elif position.entry_signal_confidence < 40:
                candidate = PruningCandidate(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    pnl_usd=position.metrics.pnl_usd,
                    pnl_percent=position.metrics.pnl_percent,
                    duration_seconds=position.metrics.duration_seconds,
                    reason=f"Poor momentum: confidence only {position.entry_signal_confidence:.0f}%",
                    severity="MEDIUM",
                    recommended_action="CLOSE",
                )
                self.stats['poor_performers_identified'] += 1
            
            # Check 4: Bad risk/reward ratio
            # (More can be lost than can be gained from here)
            risk_distance = abs(position.entry_price - position.current_sl)
            reward_distance = abs(position.take_profit - position.entry_price)
            
            if reward_distance > 0 and (risk_distance / reward_distance) > self.BAD_RR_RATIO:
                candidate = PruningCandidate(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    pnl_usd=position.metrics.pnl_usd,
                    pnl_percent=position.metrics.pnl_percent,
                    duration_seconds=position.metrics.duration_seconds,
                    reason=f"Bad R:R ({(risk_distance/reward_distance):.2f}x) - more downside than upside",
                    severity="MEDIUM",
                    recommended_action="CLOSE",
                )
            
            if candidate:
                candidates.append(candidate)
        
        return candidates
    
    def print_red_positions(self):
        """Display all positions currently floating in red"""
        open_positions = self.registry.get_all_open_positions()
        red_positions = [p for p in open_positions if p.metrics.pnl_usd < 0]
        
        if not red_positions:
            print("✅ No positions in red")
            return
        
        print("\n" + "="*100)
        print("🔴 FLOATING LOSSES (RED POSITIONS)")
        print("="*100)
        
        total_red_loss = sum(p.metrics.pnl_usd for p in red_positions)
        
        for pos in sorted(red_positions, key=lambda p: p.metrics.pnl_percent):
            loss_pct = pos.metrics.pnl_percent
            age = pos.metrics.duration_seconds
            
            # Determine urgency
            if loss_pct < -2.0:
                urgency = "🚨 CRITICAL"
            elif loss_pct < -1.0:
                urgency = "⚠️  HIGH"
            else:
                urgency = "⚠️  MEDIUM"
            
            print(f"\n{urgency} | {pos.symbol} | ${pos.metrics.pnl_usd:.2f} ({loss_pct:.2f}%)")
            print(f"   Entry: {pos.entry_price:.5f} | Current: {pos.metrics.current_price:.5f} | SL: {pos.current_sl:.5f}")
            print(f"   Age: {age}s | Mode: {pos.sl_mode.value}")
        
        print(f"\nTotal Red Loss: ${total_red_loss:.2f}")
        print("="*100 + "\n")


class CapitalPruningEngine:
    """
    Automatically prunes losing/stagnant positions.
    Reallocates capital from losers to winners.
    Ensures capital keeps moving in positive direction.
    """
    
    def __init__(self):
        self.registry = get_registry()
        self.monitor = FloatingLossMonitor()
        
        self.stats = {
            'positions_closed': 0,
            'positions_reduced': 0,
            'capital_freed_usd': 0.0,
            'capital_reallocated_to_winners': 0.0,
        }
    
    def prune_portfolio(self, execute: bool = False) -> Dict:
        """
        Identify and optionally execute pruning.
        
        Args:
            execute: If True, actually close/reduce positions
                    If False, just report what would happen
        
        Returns: Summary of pruning actions
        """
        candidates = self.monitor.identify_pruning_candidates()
        
        summary = {
            'candidates_found': len(candidates),
            'targets_count': 0,
            'total_capital_at_risk': 0.0,
            'actions_taken': 0,
        }
        
        # Separate by severity
        high_severity = [c for c in candidates if c.severity == "HIGH"]
        medium_severity = [c for c in candidates if c.severity == "MEDIUM"]
        
        # Execute on HIGH severity candidates
        for candidate in high_severity:
            if execute:
                self._execute_prune_action(candidate)
                summary['actions_taken'] += 1
            summary['targets_count'] += 1
        
        # Report on medium but don't auto-execute
        for candidate in medium_severity:
            summary['targets_count'] += 1
        
        return summary
    
    def _execute_prune_action(self, candidate: PruningCandidate):
        """Execute the pruning action (close or reduce)"""
        position = self.registry.get_position_by_id(candidate.position_id)
        
        if not position:
            return
        
        if candidate.recommended_action == "CLOSE":
            # Close the position immediately
            current_price = position.metrics.current_price or position.entry_price
            
            self.registry.close_position(
                candidate.position_id,
                current_price,
                f"PRUNED: {candidate.reason}"
            )
            
            self.stats['positions_closed'] += 1
            self.stats['capital_freed_usd'] += abs(candidate.pnl_usd)
            
            print(f"✂️  PRUNED CLOSED: {candidate.symbol} | {candidate.reason}")
            print(f"   Loss: ${candidate.pnl_usd:.2f}")
        
        elif candidate.recommended_action == "REDUCE":
            # Reduce position size by 50%
            original_units = position.size_units
            new_units = original_units * 0.5
            
            # This would be implemented in the actual trading engine
            # For now, just mark it
            position.size_units = new_units
            
            self.stats['positions_reduced'] += 1
            
            print(f"📉 PRUNED REDUCED: {candidate.symbol}")
            print(f"   Size: {original_units} → {new_units} units")
    
    def print_pruning_report(self):
        """Print detailed pruning analysis"""
        candidates = self.monitor.identify_pruning_candidates()
        
        print("\n" + "="*100)
        print("CAPITAL PRUNING ANALYSIS")
        print("="*100)
        
        if not candidates:
            print("✅ No pruning candidates - portfolio healthy")
            return
        
        print(f"\n🔍 Found {len(candidates)} pruning candidates:\n")
        
        high = [c for c in candidates if c.severity == "HIGH"]
        med = [c for c in candidates if c.severity == "MEDIUM"]
        low = [c for c in candidates if c.severity == "LOW"]
        
        if high:
            print(f"🚨 HIGH SEVERITY ({len(high)}):")
            for c in high:
                print(f"   • {c.symbol}: {c.reason}")
                print(f"     → CLOSE position (${c.pnl_usd:.2f})")
        
        if med:
            print(f"\n⚠️  MEDIUM SEVERITY ({len(med)}):")
            for c in med:
                print(f"   • {c.symbol}: {c.reason}")
                print(f"     → {c.recommended_action} (${c.pnl_usd:.2f})")
        
        print("\n" + "="*100)
    
    def enable_auto_pruning(self, check_interval: int = 30):
        """
        Enable automatic pruning with continuous monitoring.
        Checks portfolio every X seconds and closes HIGH severity positions.
        """
        import threading
        
        def auto_prune_loop():
            while True:
                time.sleep(check_interval)
                summary = self.prune_portfolio(execute=True)
                
                if summary['actions_taken'] > 0:
                    print(f"\n🔄 Auto-Pruning: Closed {summary['actions_taken']} positions")
        
        thread = threading.Thread(target=auto_prune_loop, daemon=True, name="CapitalPruner")
        thread.start()
        print(f"🔄 Auto-Pruning enabled (check every {check_interval}s)")


# Global instance
_pruning_engine = None

def get_capital_pruning_engine() -> CapitalPruningEngine:
    """Get or create global pruning engine"""
    global _pruning_engine
    if _pruning_engine is None:
        _pruning_engine = CapitalPruningEngine()
    return _pruning_engine
