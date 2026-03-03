#!/usr/bin/env python3
"""
BorgQueen Multi-Agent System: Base Agent & Protocol
PIN: 841921

All agents (Alpha, Risk, Audit) communicate via AgentSignal dataclass
through a central message bus orchestrated by BorgQueen.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime, timezone
import asyncio
import json


class AgentType(Enum):
    """Agent roles in the swarm"""
    ALPHA_TECHNICAL = "alpha_technical"     # Signal generation
    RISK_PORTFOLIO  = "risk_portfolio"      # Portfolio risk checks
    AUDIT_COMPLIANCE = "audit_compliance"   # Logging + decision chain


class SignalAction(Enum):
    """What an agent signal authorizes"""
    ALLOW = "allow"
    BLOCK = "block"
    SCALE = "scale"  # Reduce size/margin


@dataclass
class AgentSignal:
    """
    Message protocol: One agent sends this to the orchestrator (BorgQueen).
    The orchestrator aggregates decisions from all agents.
    """
    # --- Identification ---
    agent_type: AgentType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str = ""  # Unique ID for tracing this decision
    
    # --- Input Context ---
    symbol: str = ""
    direction: str = ""  # BUY / SELL
    entry_price: float = 0.0
    units: int = 0
    notional_usd: float = 0.0
    
    # --- Decision ---
    action: SignalAction = SignalAction.ALLOW  # ALLOW / BLOCK / SCALE
    confidence: float = 0.0  # 0.0 - 1.0
    reason: str = ""  # Why this decision
    
    # --- Payload (agent-specific details) ---
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # --- Tracing ---
    version: str = "1.0"
    checksum: str = ""  # Optional validation hash
    
    def __post_init__(self):
        """Validate and auto-generate missing fields"""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.request_id:
            import time
            self.request_id = f"{self.agent_type.value}_{int(time.time()*1000)}"
    
    def is_blocking(self) -> bool:
        """Returns True if this signal blocks the trade"""
        return self.action == SignalAction.BLOCK or self.confidence < 0.3
    
    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dict"""
        return {
            "agent_type": self.agent_type.value,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "units": self.units,
            "notional_usd": self.notional_usd,
            "action": self.action.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "payload": self.payload,
            "version": self.version,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict())


@dataclass
class DecisionChain:
    """
    Aggregated decision from all agents for one trade attempt.
    Logged to narration for full audit trail.
    """
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    units: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Alpha signal
    alpha_signal: Optional[AgentSignal] = None
    
    # Risk gates
    risk_signals: List[AgentSignal] = field(default_factory=list)
    
    # Final decision
    final_decision: SignalAction = SignalAction.ALLOW
    final_confidence: float = 0.0
    decision_reason: str = ""
    
    # Full trace
    all_signals: List[AgentSignal] = field(default_factory=list)
    
    def is_approved(self) -> bool:
        """Trade approved if final_decision is ALLOW and conf >= 0.5"""
        return (self.final_decision == SignalAction.ALLOW and 
                self.final_confidence >= 0.5)
    
    def to_dict(self) -> Dict:
        """Serialize for narration"""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "units": self.units,
            "timestamp": self.timestamp,
            "alpha_signal": self.alpha_signal.to_dict() if self.alpha_signal else None,
            "risk_signals": [s.to_dict() for s in self.risk_signals],
            "final_decision": self.final_decision.value,
            "final_confidence": self.final_confidence,
            "decision_reason": self.decision_reason,
            "signal_count": len(self.all_signals),
        }


class BaseAgent:
    """
    Abstract base for all MAS agents.
    All agents inherit this and override process_signal().
    """
    
    def __init__(self, agent_type: AgentType, name: str = ""):
        self.agent_type = agent_type
        self.name = name or agent_type.value
        self.logger = None  # Will be set by orchestrator
        self.stats = {
            "signals_processed": 0,
            "blocks_issued": 0,
            "allows_issued": 0,
        }
    
    async def process_signal(self, signal_input: Dict) -> AgentSignal:
        """
        Main processing method — override in subclasses.
        
        Args:
            signal_input: Dict with symbol, direction, entry_price, units, etc.
        
        Returns:
            AgentSignal with decision
        """
        raise NotImplementedError(f"{self.name} must implement process_signal()")
    
    def update_stats(self, signal: AgentSignal):
        """Track decision stats"""
        self.stats["signals_processed"] += 1
        if signal.action == SignalAction.BLOCK:
            self.stats["blocks_issued"] += 1
        elif signal.action == SignalAction.ALLOW:
            self.stats["allows_issued"] += 1
    
    def log(self, msg: str, level: str = "INFO"):
        """Log via orchestrator logger if available"""
        prefix = f"[{self.name}]"
        if self.logger:
            getattr(self.logger, level.lower(), print)(f"{prefix} {msg}")
        else:
            print(f"{prefix} {msg}")
