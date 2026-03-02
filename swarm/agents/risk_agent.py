#!/usr/bin/env python3
"""
Risk Agent: Portfolio Constraint Enforcement
PIN: 841921

Evaluates:
- Margin utilization
- Correlation exposure (same currency, same side)
- Max position limits
- Notional floor
"""

import asyncio
from typing import Dict
from swarm.agents.base_agent import BaseAgent, AgentSignal, AgentType, SignalAction


class RiskAgent(BaseAgent):
    """
    Portfolio risk gating.
    
    Inputs:
      - symbol, direction, units, notional_usd, entry_price
      - current_positions (list of open trades)
      - account_nav, current_margin_used
    
    Outputs:
      - AgentSignal: ALLOW if risk gates pass, BLOCK if violated
    """
    
    def __init__(
        self,
        max_margin_pct: float = 0.35,
        min_notional_usd: float = 15000.0,
        max_positions: int = 5,
        max_same_currency_exposure: float = 0.50,
    ):
        super().__init__(
            agent_type=AgentType.RISK_PORTFOLIO,
            name="RiskAgent"
        )
        self.max_margin_pct = max_margin_pct
        self.min_notional_usd = min_notional_usd
        self.max_positions = max_positions
        self.max_same_currency_exposure = max_same_currency_exposure
    
    async def process_signal(self, signal_input: Dict) -> AgentSignal:
        """
        Evaluate portfolio risk constraints.
        
        Args:
            signal_input: {
                symbol, direction, entry_price, units, notional_usd,
                current_positions (list),
                account_nav, current_margin_used
            }
        
        Returns:
            AgentSignal: BLOCK if risk violated, ALLOW otherwise
        """
        import time
        request_id = f"risk_{int(time.time()*1000)}"
        
        symbol = signal_input.get("symbol", "")
        direction = signal_input.get("direction", "")
        units = signal_input.get("units", 0)
        notional_usd = signal_input.get("notional_usd", 0.0)
        entry_price = signal_input.get("entry_price", 0.0)
        current_positions = signal_input.get("current_positions", [])
        account_nav = signal_input.get("account_nav", 10000.0)
        current_margin_used = signal_input.get("current_margin_used", 0.0)
        
        blocks = []
        
        # ─── Gate 1: Notional floor ────────────────────────────────────────
        if notional_usd < self.min_notional_usd:
            blocks.append(
                f"notional ${notional_usd:,.0f} < ${self.min_notional_usd:,} floor"
            )
        
        # ─── Gate 2: Max positions ────────────────────────────────────────
        if len(current_positions) >= self.max_positions:
            blocks.append(
                f"open positions {len(current_positions)} >= max {self.max_positions}"
            )
        
        # ─── Gate 3: Margin cap ────────────────────────────────────────────
        # Estimate margin: notional * 0.02 (50:1 leverage)
        est_margin = notional_usd * 0.02
        proj_margin = current_margin_used + est_margin
        proj_margin_pct = proj_margin / max(account_nav, 1)
        
        if proj_margin_pct > self.max_margin_pct:
            blocks.append(
                f"projected margin {proj_margin_pct:.1%} > {self.max_margin_pct:.1%} cap"
            )
        
        # ─── Gate 4: Currency correlation ──────────────────────────────────
        # Block if adding a 2nd trade in same currency on same side
        base, quote = symbol.split("_")[0], symbol.split("_")[1]
        same_ccy_same_side = [
            p for p in current_positions
            if (base in p.get("symbol", "") or quote in p.get("symbol", ""))
            and p.get("direction") == direction
        ]
        
        if len(same_ccy_same_side) >= 1:
            blocks.append(
                f"already {len(same_ccy_same_side)} {direction} position(s) "
                f"in {base}/{quote} currencies"
            )
        
        # ─── Decision ──────────────────────────────────────────────────────
        if blocks:
            decision = SignalAction.BLOCK
            reason = "; ".join(blocks)
            confidence = 0.0
        else:
            decision = SignalAction.ALLOW
            reason = (
                f"margin {proj_margin_pct:.1%} OK, "
                f"positions {len(current_positions)}/{self.max_positions}, "
                f"notional OK"
            )
            confidence = 0.95  # Risk gates are binary
        
        signal = AgentSignal(
            agent_type=AgentType.RISK_PORTFOLIO,
            request_id=request_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            units=units,
            notional_usd=notional_usd,
            action=decision,
            confidence=confidence,
            reason=reason,
            payload={
                "current_margin_pct": current_margin_used / max(account_nav, 1),
                "projected_margin_pct": proj_margin_pct,
                "max_margin_pct": self.max_margin_pct,
                "open_positions": len(current_positions),
                "max_positions": self.max_positions,
                "same_currency_exposure": len(same_ccy_same_side),
            }
        )
        
        self.update_stats(signal)
        return signal
