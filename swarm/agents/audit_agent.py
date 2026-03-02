#!/usr/bin/env python3
"""
Audit Agent: Decision Chain Logging
PIN: 841921

Logs all trade decisions to narration.jsonl for full compliance audit.
Computes Sharpe, MDD, decision chain metrics.
"""

import asyncio
import json
import os
from typing import Dict
from datetime import datetime, timezone
from swarm.agents.base_agent import BaseAgent, AgentSignal, AgentType, SignalAction


class AuditAgent(BaseAgent):
    """
    Compliance & audit logging.
    
    For each trade decision, logs:
    - All agent signals (Alpha, Risk)
    - Final decision + reasoning
    - Market context (price, confidence, etc.)
    - Aggregated metrics (Sharpe, MDD)
    """
    
    def __init__(self, audit_log_path: str = None):
        super().__init__(
            agent_type=AgentType.AUDIT_COMPLIANCE,
            name="AuditAgent"
        )
        self.audit_log_path = (
            audit_log_path or 
            os.path.expanduser("~") + "/RBOTZILLA_PHOENIX/logs/audit_trail.jsonl"
        )
        self.pnl_history = []  # Track P&L for Sharpe/MDD
        self.max_dd = 0.0
        self.max_dd_from = 0.0
    
    async def process_signal(self, signal_input: Dict) -> AgentSignal:
        """
        Log decision for audit trail.
        
        Args:
            signal_input: Trade context (symbol, direction, etc.)
        
        Returns:
            AgentSignal (always ALLOW — audit doesn't block, only logs)
        """
        import time
        request_id = f"audit_{int(time.time()*1000)}"
        
        # ─── Extract context ──────────────────────────────────────────────
        symbol = signal_input.get("symbol", "")
        direction = signal_input.get("direction", "")
        entry_price = signal_input.get("entry_price", 0.0)
        units = signal_input.get("units", 0)
        notional_usd = signal_input.get("notional_usd", 0.0)
        
        # Optional: pnl for live trade metrics
        current_pnl = signal_input.get("current_pnl", 0.0)
        
        # ─── Update metrics ────────────────────────────────────────────────
        if current_pnl != 0:
            self.pnl_history.append(current_pnl)
            self._update_drawdown(current_pnl)
        
        # ─── Build audit record ────────────────────────────────────────────
        audit_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "trade_context": {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "units": units,
                "notional_usd": notional_usd,
            },
            "metrics": {
                "total_pnl": sum(self.pnl_history),
                "max_drawdown": self.max_dd,
                "trades_logged": len(self.pnl_history),
            },
            "compliance": {
                "charter_pin": "841921",
                "audit_version": "1.0",
                "min_notional_checked": notional_usd >= 15000.0,
            }
        }
        
        # ─── Write to JSONL ────────────────────────────────────────────────
        try:
            os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
            with open(self.audit_log_path, "a") as f:
                f.write(json.dumps(audit_record) + "\n")
        except Exception as e:
            self.log(f"Audit log write failed: {e}", level="WARNING")
        
        # ─── Return signal (always ALLOW — audit is non-blocking) ──────────
        signal = AgentSignal(
            agent_type=AgentType.AUDIT_COMPLIANCE,
            request_id=request_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            units=units,
            notional_usd=notional_usd,
            action=SignalAction.ALLOW,
            confidence=1.0,  # Always allows
            reason="Audit logged",
            payload=audit_record
        )
        
        self.update_stats(signal)
        return signal
    
    def _update_drawdown(self, pnl: float):
        """Track maximum drawdown"""
        cumsum = sum(self.pnl_history)
        if cumsum > self.max_dd_from:
            self.max_dd_from = cumsum
        self.max_dd = max(self.max_dd, self.max_dd_from - cumsum)
    
    def get_audit_summary(self) -> Dict:
        """Return audit metrics"""
        total_pnl = sum(self.pnl_history)
        
        if len(self.pnl_history) <= 1:
            sharpe = 0.0
        else:
            import statistics
            mean_pnl = total_pnl / len(self.pnl_history)
            std_pnl = statistics.stdev(self.pnl_history) if len(self.pnl_history) > 1 else 0.0001
            sharpe = (mean_pnl / std_pnl) if std_pnl > 0 else 0.0
        
        return {
            "total_pnl": total_pnl,
            "trades_logged": len(self.pnl_history),
            "max_drawdown": self.max_dd,
            "sharpe_ratio": sharpe,
            "audit_log_path": self.audit_log_path,
        }
