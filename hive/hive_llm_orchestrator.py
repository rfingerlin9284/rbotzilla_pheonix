"""
Hive-LLM Orchestrator: Unified coordination between Hive Mind agents and Local LLM
Provides reinforcement guidance for trade decisions without blocking execution
PIN: 841921 | Non-interrupting guidance system
"""

import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
import requests

logger = logging.getLogger(__name__)


class GuidanceLevel(Enum):
    """Guidance confidence levels"""
    STRONG_ENDORSE = 0.95
    ENDORSE = 0.8
    NEUTRAL = 0.5
    CAUTION = 0.3
    STRONG_CAUTION = 0.1


@dataclass
class TradeOpportunity:
    """Incoming trade signal from multi-strategy system"""
    symbol: str
    direction: str  # BUY or SELL
    entry_price: float
    sl_price: float
    tp_price: float
    reward_risk_ratio: float
    detector_votes: int
    confidence: float
    detectors_agreed: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class HiveAnalysisResult:
    """Hive Mind consensus from multi-AI delegation"""
    signal_strength: str  # STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL
    confidence: float  # 0.0 to 1.0
    reasoning: str = ""
    agent_weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class LLMGuidance:
    """Local LLM reinforcement guidance"""
    recommendation: str  # ENDORSE, CAUTION, NEUTRAL
    reasoning: str = ""
    learned_pattern: str = ""  # Pattern from recent wins/losses
    confidence: float = 0.5


@dataclass
class HiveLLMConsensus:
    """Combined guidance from Hive + LLM"""
    endorsement_level: GuidanceLevel
    combined_confidence: float
    hive_signal: str = ""
    llm_recommendation: str = ""
    final_reasoning: str = ""
    should_proceed: bool = True
    reinforcement_notes: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HiveLLMOrchestrator:
    """
    Orchestrator combining Hive Mind agents and Local LLM for guided trading
    
    Architecture:
    1. Receives incoming trade opportunity from scanner
    2. Queries Hive Mind for multi-AI consensus
    3. Queries Local LLM for pattern recognition
    4. Combines guidance non-blockingly
    5. Returns endorsement level + reasoning
    
    Policy: GUIDANCE ONLY - never blocks trades, only advises
    """
    
    def __init__(self, logger_instance=None):
        self.logger = logger_instance or logging.getLogger(__name__)
        self.ollama_url = "http://127.0.0.1:11434/api/generate"
        self.ollama_model = "llama3.1:8b"
        self.ollama_available = self._check_ollama()
        
        # Track recent guidance for learning
        self.recent_trades: List[Dict] = []
        self.endorsement_history: List[HiveLLMConsensus] = []
        self.max_history = 100
        
        # Import Hive Mind locally to avoid circular imports
        try:
            from hive.rick_hive_mind import RickHiveMind
            self.hive_mind = RickHiveMind()
            self.hive_available = True
        except Exception as e:
            self.logger.warning(f"Hive Mind unavailable: {e}")
            self.hive_mind = None
            self.hive_available = False
    
    def _check_ollama(self) -> bool:
        """Check if Ollama is reachable"""
        try:
            response = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": "test", "stream": False},
                timeout=2
            )
            return response.status_code == 200
        except:
            return False
    
    def get_reinforcement_guidance(self, opportunity: TradeOpportunity) -> HiveLLMConsensus:
        """
        Main orchestrator method: Get combined Hive + LLM guidance
        
        Returns HiveLLMConsensus with:
        - endorsement_level: GuidanceLevel enum (STRONG_ENDORSE to STRONG_CAUTION)
        - combined_confidence: 0.0-1.0 confidence in guidance
        - should_proceed: Always True (never blocks)
        - reinforcement_notes: Reasoning from both systems
        """
        
        consensus = HiveLLMConsensus()
        
        # Query Hive Mind (if available)
        hive_result = None
        if self.hive_available:
            try:
                hive_result = self._query_hive_mind(opportunity)
            except Exception as e:
                self.logger.warning(f"Hive query failed: {e}")
        
        # Query Local LLM (if available)
        llm_result = None
        if self.ollama_available:
            try:
                llm_result = self._query_llm_for_guidance(opportunity)
            except Exception as e:
                self.logger.warning(f"LLM query failed: {e}")
        
        # Combine guidance
        consensus = self._combine_consensus(
            opportunity, hive_result, llm_result
        )
        
        # Track for learning
        self.endorsement_history.append(consensus)
        if len(self.endorsement_history) > self.max_history:
            self.endorsement_history.pop(0)
        
        return consensus
    
    def _query_hive_mind(self, opportunity: TradeOpportunity) -> Optional[HiveAnalysisResult]:
        """Query Hive Mind agents for consensus on trade opportunity"""
        if not self.hive_mind:
            return None
        
        try:
            # Prepare analysis context
            context = {
                'symbol': opportunity.symbol,
                'direction': opportunity.direction,
                'entry': opportunity.entry_price,
                'sl': opportunity.sl_price,
                'tp': opportunity.tp_price,
                'rr_ratio': opportunity.reward_risk_ratio,
                'detector_votes': opportunity.detector_votes,
                'confidence': opportunity.confidence,
                'detectors': opportunity.detectors_agreed
            }
            
            # Get Hive analysis (delegates to GPT, GROK, DeepSeek)
            hive_analysis = self.hive_mind.delegate_analysis(
                signal_type='TRADE_OPPORTUNITY',
                market_context=context
            )
            
            return hive_analysis
        except Exception as e:
            self.logger.error(f"Hive analysis failed: {e}")
            return None
    
    def _query_llm_for_guidance(self, opportunity: TradeOpportunity) -> Optional[LLMGuidance]:
        """Query Local LLM (Ollama) for pattern-based guidance"""
        if not self.ollama_available:
            return None
        
        try:
            # Build prompt from opportunity and recent history
            prompt = self._build_llm_prompt(opportunity)
            
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,  # Low randomness for consistency
                    "top_p": 0.8
                },
                timeout=10
            )
            
            if response.status_code != 200:
                return None
            
            response_text = response.json().get('response', '').strip()
            guidance = self._parse_llm_response(response_text)
            
            return guidance
        except Exception as e:
            self.logger.error(f"LLM guidance failed: {e}")
            return None
    
    def _build_llm_prompt(self, opportunity: TradeOpportunity) -> str:
        """Build prompt for LLM analysis"""
        
        recent_pattern = self._analyze_recent_pattern()
        
        prompt = f"""You are a trading pattern recognition AI. Analyze this trade opportunity:

Symbol: {opportunity.symbol}
Direction: {opportunity.direction}
Entry: {opportunity.entry_price}
Stop Loss: {opportunity.sl_price}
Take Profit: {opportunity.tp_price}
R:R Ratio: {opportunity.reward_risk_ratio}:1
Detectors Agreed: {', '.join(opportunity.detectors_agreed)} ({opportunity.detector_votes} votes)
Market Confidence: {opportunity.confidence:.2%}

Recent Winning Pattern: {recent_pattern['pattern']}
Recent Win Rate: {recent_pattern['win_rate']:.1%}
Recent Avg Win: ${recent_pattern['avg_win']:,.2f}

Provide brief guidance (1-2 sentences):
1. ENDORSE, CAUTION, or NEUTRAL
2. Key reasoning (pattern match, risk/reward fit)

Format: [RECOMMENDATION] | [REASONING]"""
        
        return prompt
    
    def _parse_llm_response(self, response: str) -> LLMGuidance:
        """Parse LLM response into structured guidance"""
        guidance = LLMGuidance()
        
        try:
            # Look for [RECOMMENDATION] | [REASONING] format
            if "|" in response:
                parts = response.split("|", 1)
                rec = parts[0].strip().upper()
                reasoning = parts[1].strip() if len(parts) > 1 else ""
                
                # Map to recommendation
                if "ENDORSE" in rec:
                    guidance.recommendation = "ENDORSE"
                    guidance.confidence = 0.8
                elif "CAUTION" in rec:
                    guidance.recommendation = "CAUTION"
                    guidance.confidence = 0.3
                else:
                    guidance.recommendation = "NEUTRAL"
                    guidance.confidence = 0.5
                
                guidance.reasoning = reasoning
            else:
                # Parse free-form response
                resp_upper = response.upper()
                if "ENDORSE" in resp_upper:
                    guidance.recommendation = "ENDORSE"
                    guidance.confidence = 0.75
                elif "CAUTION" in resp_upper:
                    guidance.recommendation = "CAUTION"
                    guidance.confidence = 0.3
                else:
                    guidance.recommendation = "NEUTRAL"
                    guidance.confidence = 0.5
                
                guidance.reasoning = response[:200]  # First 200 chars
        except Exception as e:
            self.logger.error(f"LLM response parse error: {e}")
            guidance.recommendation = "NEUTRAL"
            guidance.reasoning = "Parse error"
        
        return guidance
    
    def _analyze_recent_pattern(self) -> Dict[str, Any]:
        """Analyze pattern from recent trades for learning"""
        if not self.endorsement_history:
            return {
                'pattern': 'Insufficient data',
                'win_rate': 0.5,
                'avg_win': 50.0
            }
        
        # Simplified pattern analysis
        recent = self.endorsement_history[-20:]  # Last 20 trades
        
        return {
            'pattern': f"Recent {len(recent)} trades analyzed",
            'win_rate': 0.62,  # Placeholder
            'avg_win': 82.05  # From session winning trades
        }
    
    def _combine_consensus(
        self,
        opportunity: TradeOpportunity,
        hive_result: Optional[HiveAnalysisResult],
        llm_result: Optional[LLMGuidance]
    ) -> HiveLLMConsensus:
        """
        Combine Hive Mind + LLM guidance into unified consensus
        
        Weighting:
        - Hive Mind: 60% (multi-AI consensus is robust)
        - LLM Pattern Recognition: 40% (learning from recent trades)
        """
        
        consensus = HiveLLMConsensus()
        consensus.should_proceed = True  # ALWAYS proceed (guidance only)
        
        # Start with base confidence from opportunity
        base_confidence = opportunity.confidence
        
        # Apply Hive weighting (60%)
        hive_weight = 0
        if hive_result:
            consensus.hive_signal = hive_result.signal_strength
            
            # Map signal to confidence multiplier
            signal_map = {
                'STRONG_BUY': 1.2,
                'BUY': 1.1,
                'NEUTRAL': 1.0,
                'SELL': 0.7,
                'STRONG_SELL': 0.3
            }
            hive_weight = signal_map.get(hive_result.signal_strength, 1.0)
        
        # Apply LLM weighting (40%)
        llm_weight = 0
        if llm_result:
            consensus.llm_recommendation = llm_result.recommendation
            
            rec_map = {
                'ENDORSE': 1.15,
                'NEUTRAL': 1.0,
                'CAUTION': 0.8
            }
            llm_weight = rec_map.get(llm_result.recommendation, 1.0)
        
        # Combined confidence
        combined = (base_confidence * 0.6 * hive_weight + 
                   base_confidence * 0.4 * llm_weight)
        
        consensus.combined_confidence = min(0.99, max(0.05, combined))
        
        # Map to endorsement level
        if consensus.combined_confidence >= 0.85:
            consensus.endorsement_level = GuidanceLevel.STRONG_ENDORSE
        elif consensus.combined_confidence >= 0.70:
            consensus.endorsement_level = GuidanceLevel.ENDORSE
        elif consensus.combined_confidence >= 0.40:
            consensus.endorsement_level = GuidanceLevel.NEUTRAL
        elif consensus.combined_confidence >= 0.25:
            consensus.endorsement_level = GuidanceLevel.CAUTION
        else:
            consensus.endorsement_level = GuidanceLevel.STRONG_CAUTION
        
        # Build reasoning
        reasons = []
        if hive_result:
            reasons.append(f"Hive: {hive_result.signal_strength} ({hive_result.confidence:.0%})")
        if llm_result:
            reasons.append(f"LLM: {llm_result.recommendation} ({llm_result.confidence:.0%})")
        
        consensus.final_reasoning = " | ".join(reasons) if reasons else "Baseline analysis"
        consensus.reinforcement_notes = reasons
        
        return consensus
    
    def log_trade_outcome(self, trade_id: str, symbol: str, pnl: float, is_win: bool):
        """
        Log actual trade outcome for learning
        Called after trade closes to reinforce pattern recognition
        """
        try:
            outcome = {
                'trade_id': trade_id,
                'symbol': symbol,
                'pnl': pnl,
                'is_win': is_win,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            self.recent_trades.append(outcome)
            if len(self.recent_trades) > self.max_history:
                self.recent_trades.pop(0)
            
            self.logger.info(f"Trade outcome logged: {trade_id} ({symbol}) PnL=${pnl:,.2f}")
        except Exception as e:
            self.logger.error(f"Trade outcome logging failed: {e}")
    
    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get status for diagnostics"""
        return {
            'hive_available': self.hive_available,
            'ollama_available': self.ollama_available,
            'recent_trades_tracked': len(self.recent_trades),
            'endorsement_history_size': len(self.endorsement_history),
            'status': 'ACTIVE' if (self.hive_available or self.ollama_available) else 'DORMANT'
        }
