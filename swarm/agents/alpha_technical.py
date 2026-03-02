#!/usr/bin/env python3
"""
Alpha Technical Agent: Signal Generation
PIN: 841921

Wraps multi_signal_engine signals into AgentSignal format.
Evaluates confidence, detectors, session bias, R:R ratio.
"""

import asyncio
import logging
from typing import Dict, Optional
from swarm.agents.base_agent import BaseAgent, AgentSignal, AgentType, SignalAction


class AlphaTechnicalAgent(BaseAgent):
    """
    Signal generation agent.
    
    Inputs from multi_signal_engine:
      - symbol, direction, entry_price, units, notional_usd
      - confidence, votes, detectors_fired, session, rr
      - sl, tp (from signal)
    
    Outputs:
      - AgentSignal with ALLOW/BLOCK + confidence
      - Payload includes detector breakdown
    """
    
    def __init__(self, min_confidence: float = 0.62):
        super().__init__(
            agent_type=AgentType.ALPHA_TECHNICAL,
            name="AlphaTechnicalAgent"
        )
        self.min_confidence = min_confidence
        self.min_rr_ratio = 3.2  # Charter immutable
    
    async def process_signal(self, signal_input: Dict) -> AgentSignal:
        """
        Evaluate multi_signal_engine output.
        
        Args:
            signal_input: {
                symbol, direction, entry_price, units, notional_usd,
                confidence, votes, detectors_fired, session, rr,
                sl, tp
            }
        
        Returns:
            AgentSignal with decision
        """
        import time
        request_id = f"alpha_{int(time.time()*1000)}"
        
        symbol = signal_input.get("symbol", "")
        direction = signal_input.get("direction", "")
        entry_price = signal_input.get("entry_price", 0.0)
        units = signal_input.get("units", 0)
        notional_usd = signal_input.get("notional_usd", 0.0)
        confidence = signal_input.get("confidence", 0.0)
        votes = signal_input.get("votes", 0)
        detectors = signal_input.get("detectors_fired", [])
        session = signal_input.get("session", "unknown")
        rr = signal_input.get("rr", 0.0)
        sl = signal_input.get("sl", 0.0)
        tp = signal_input.get("tp", 0.0)
        
        # ─── Validation gates ──────────────────────────────────────────────
        blocks = []
        
        if confidence < 0.5:
            blocks.append(f"confidence {confidence:.1%} < 50% floor")
        
        if confidence < self.min_confidence:
            blocks.append(f"confidence {confidence:.1%} < {self.min_confidence:.1%} gate")
        
        if votes < 2:
            blocks.append(f"only {votes} detector votes (min 2)")
        
        if not detectors:
            blocks.append("no detectors fired")
        
        if rr < self.min_rr_ratio:
            blocks.append(f"R:R {rr:.2f}:1 < {self.min_rr_ratio}:1 charter")
        
        # ─── Decision ──────────────────────────────────────────────────────
        if blocks:
            decision = SignalAction.BLOCK
            reason = "; ".join(blocks)
            final_confidence = 0.0
        else:
            decision = SignalAction.ALLOW
            reason = f"{len(detectors)} detectors agree: {','.join(detectors)}"
            final_confidence = confidence  # Pass confidence from engine
        
        # ─── Build signal ──────────────────────────────────────────────────
        signal = AgentSignal(
            agent_type=AgentType.ALPHA_TECHNICAL,
            request_id=request_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            units=units,
            notional_usd=notional_usd,
            action=decision,
            confidence=final_confidence,
            reason=reason,
            payload={
                "votes": votes,
                "detectors": detectors,
                "session": session,
                "rr_ratio": rr,
                "sl": sl,
                "tp": tp,
                "raw_confidence": confidence,
                "min_confidence_gate": self.min_confidence,
                "min_rr_charter": self.min_rr_ratio,
            }
        )
        
        self.update_stats(signal)
        return signal
