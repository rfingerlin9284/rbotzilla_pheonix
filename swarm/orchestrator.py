#!/usr/bin/env python3
"""
BorgQueen: Multi-Agent Orchestrator
PIN: 841921

Central message bus for all agents (Alpha, Risk, Audit).
Aggregates decisions, enforces conflict resolution, logs audit chain.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone
import json

from swarm.agents.base_agent import (
    BaseAgent, AgentSignal, AgentType, SignalAction, DecisionChain
)


class BorgQueenOrchestrator:
    """
    Central orchestrator for multi-agent decision-making.
    
    Flow:
      1. New trade signal arrives (from multi_signal_engine)
      2. Alpha agent processes the signal (generates trade)
      3. Risk agents evaluate portfolio impact
      4. Audit logs the full decision chain
      5. Orchestrator returns final ALLOW/BLOCK decision
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger("BorgQueen")
        self.agents: Dict[AgentType, BaseAgent] = {}
        self.decision_queue: asyncio.Queue = asyncio.Queue()
        self.audit_log: List[DecisionChain] = []
        self.conflict_resolution = "CONSERVATIVE"  # ALLOW only if all agents allow
        self.stats = {
            "trades_evaluated": 0,
            "trades_approved": 0,
            "trades_blocked": 0,
            "avg_decision_time_ms": 0,
        }
    
    def register_agent(self, agent: BaseAgent):
        """Register an agent with the orchestrator"""
        self.agents[agent.agent_type] = agent
        agent.logger = self.logger
        self.logger.info(f"✅ Agent registered: {agent.name}")
    
    async def process_trade_request(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        units: int,
        notional_usd: float,
        trade_id: str = "",
        context: Dict = None
    ) -> DecisionChain:
        """
        Multi-agent evaluation of a single trade.
        
        Args:
            symbol: e.g., 'EUR_USD'
            direction: 'BUY' or 'SELL'
            entry_price: Entry level
            units: Position size
            notional_usd: USD notional value
            trade_id: Unique ID for audit trail
            context: Additional context (strategy name, signal source, etc.)
        
        Returns:
            DecisionChain with final decision + full audit
        """
        import time
        start_time = time.time()
        
        if not trade_id:
            trade_id = f"trade_{int(time.time()*1000)}"
        
        decision = DecisionChain(
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            units=units,
        )
        
        signal_input = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "units": units,
            "notional_usd": notional_usd,
            **(context or {}),
        }
        
        # ─── Phase 1: Alpha (signal source) ──────────────────────────────
        if AgentType.ALPHA_TECHNICAL in self.agents:
            alpha_agent = self.agents[AgentType.ALPHA_TECHNICAL]
            try:
                alpha_signal = await alpha_agent.process_signal(signal_input)
                decision.alpha_signal = alpha_signal
                decision.all_signals.append(alpha_signal)
                
                if alpha_signal.is_blocking():
                    decision.final_decision = SignalAction.BLOCK
                    decision.final_confidence = alpha_signal.confidence
                    decision.decision_reason = f"Alpha block: {alpha_signal.reason}"
                    self.stats["trades_blocked"] += 1
                    self.logger.warning(
                        f"⛔ {symbol} {direction}: Alpha blocked — {alpha_signal.reason}"
                    )
                    return decision
            except Exception as e:
                self.logger.error(f"❌ Alpha agent error: {e}")
                decision.final_decision = SignalAction.BLOCK
                decision.decision_reason = f"Alpha error: {str(e)}"
                return decision
        
        # ─── Phase 2: Risk agents ──────────────────────────────────────────
        risk_blocks = []
        for agent_type, agent in self.agents.items():
            if agent_type == AgentType.RISK_PORTFOLIO:
                try:
                    risk_signal = await agent.process_signal(signal_input)
                    decision.risk_signals.append(risk_signal)
                    decision.all_signals.append(risk_signal)
                    
                    if risk_signal.is_blocking():
                        risk_blocks.append(risk_signal)
                        self.logger.warning(
                            f"⚠️  {symbol}: Risk block — {risk_signal.reason}"
                        )
                except Exception as e:
                    self.logger.error(f"❌ Risk agent error: {e}")
                    risk_blocks.append(
                        AgentSignal(
                            agent_type=AgentType.RISK_PORTFOLIO,
                            action=SignalAction.BLOCK,
                            reason=f"Risk agent error: {str(e)}",
                        )
                    )
        
        if risk_blocks:
            decision.final_decision = SignalAction.BLOCK
            decision.final_confidence = 0.0
            decision.decision_reason = f"Risk blocks: {len(risk_blocks)} gates failed"
            self.stats["trades_blocked"] += 1
            return decision
        
        # ─── Phase 3: Audit agent (logging) ──────────────────────────────
        if AgentType.AUDIT_COMPLIANCE in self.agents:
            audit_agent = self.agents[AgentType.AUDIT_COMPLIANCE]
            try:
                audit_signal = await audit_agent.process_signal(signal_input)
                decision.all_signals.append(audit_signal)
            except Exception as e:
                self.logger.warning(f"⚠️  Audit agent error (non-blocking): {e}")
        
        # ─── Final Decision ───────────────────────────────────────────────
        if decision.alpha_signal:
            decision.final_decision = SignalAction.ALLOW
            decision.final_confidence = decision.alpha_signal.confidence
            decision.decision_reason = f"Alpha approved: {decision.alpha_signal.reason}"
            self.stats["trades_approved"] += 1
            
            self.logger.info(
                f"✅ {symbol} {direction} APPROVED @ {entry_price} "
                f"({units} units, ${notional_usd:,.0f} notional) "
                f"— confidence={decision.final_confidence:.1%}"
            )
        else:
            decision.final_decision = SignalAction.BLOCK
            decision.decision_reason = "No alpha signal"
            self.stats["trades_blocked"] += 1
        
        # ─── Audit log ───────────────────────────────────────────────────
        self.audit_log.append(decision)
        
        # Track decision time
        elapsed_ms = (time.time() - start_time) * 1000
        self.stats["avg_decision_time_ms"] = (
            (self.stats["avg_decision_time_ms"] * self.stats["trades_evaluated"] + 
             elapsed_ms) / (self.stats["trades_evaluated"] + 1)
        )
        self.stats["trades_evaluated"] += 1
        
        return decision
    
    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("🛑 BorgQueen shutting down...")
        for agent in self.agents.values():
            if hasattr(agent, 'shutdown'):
                await agent.shutdown()
    
    def get_audit_trail(self, trade_id: str = None) -> List[Dict]:
        """
        Retrieve audit trail for one trade or all trades.
        
        Args:
            trade_id: If provided, return only this trade's decision chain
        
        Returns:
            List of decision dicts (JSON-serializable)
        """
        if trade_id:
            for decision in self.audit_log:
                if decision.trade_id == trade_id:
                    return [decision.to_dict()]
            return []
        else:
            return [d.to_dict() for d in self.audit_log]
    
    def get_stats(self) -> Dict:
        """Return orchestrator statistics"""
        return {
            **self.stats,
            "agents_active": len(self.agents),
            "audit_log_size": len(self.audit_log),
            "approval_rate": (
                self.stats["trades_approved"] / max(self.stats["trades_evaluated"], 1)
            ),
        }
