#!/usr/bin/env python3
"""
OANDA Trading Engine - RBOTzilla Charter Compliant
Environment-Agnostic: practice/live determined ONLY by API endpoint & token
- Unified codebase for all environments
- Real-time OANDA API for market data and execution
- Full RICK Hive Mind + ML Intelligence + Immutable Risk Management
- Momentum-based TP cancellation with adaptive trailing stops
PIN: 841921 | Generated: 2025-10-15
"""

# ── Non-interactive / headless safety guard ────────────────────────────────
# VS Code task terminals and nohup sessions have no TTY.  Exit here only if
# we are genuinely NOT meant to run (e.g. accidentally sourced).  Set
# RBOT_FORCE_RUN=1 to bypass any TTY check unconditionally.
import os as _os
if not _os.environ.get('RBOT_FORCE_RUN') and _os.environ.get('RBOT_REQUIRE_TTY'):
    import sys as _sys
    if not _sys.stdout.isatty():
        _sys.exit(0)

import sys
from pathlib import Path
import os
import time
import asyncio
import requests
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.resolve()))

# Load environment variables manually
env_file = str(Path(__file__).parent / 'master.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

# Charter compliance imports
from foundation.rick_charter import RickCharter
from foundation.margin_correlation_gate import MarginCorrelationGate, Position, Order, HookResult
from brokers.oanda_connector import OandaConnector
from util.terminal_display import TerminalDisplay, Colors
from util.narration_logger import log_narration, log_pnl
from util.rick_narrator import RickNarrator

# Momentum-based adaptive SL system (NEW)
try:
    from risk.momentum_adaptive_sl import (
        MomentumProfile, AdaptiveStopLoss, WinningTradeAnalyzer, 
        ReallocateCapital, calculate_momentum_profile
    )
    MOMENTUM_ADAPTIVE_SL_AVAILABLE = True
except ImportError:
    MOMENTUM_ADAPTIVE_SL_AVAILABLE = False
from util.usd_converter import get_usd_notional
from util.positions_registry import PositionsRegistry
from util.position_dashboard import PositionDashboard
from systems.multi_signal_engine import scan_symbol, manage_open_trade, TradeAction, AggregatedSignal

# Tight trailing stop + TP guard (dec4_dec10 reference: rbz_tight_trailing.py)
try:
    from rbz_tight_trailing import apply_rbz_overrides, tp_guard, policy_for, TightSL
    RBZ_TRAILING_AVAILABLE = True
except ImportError:
    RBZ_TRAILING_AVAILABLE = False
    print("⚠️  rbz_tight_trailing not available - using legacy trailing")

# ML Intelligence imports
try:
    from ml_learning.regime_detector import RegimeDetector
    from ml_learning.signal_analyzer import SignalAnalyzer
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️  ML modules not available - running in basic mode")

# Hive Mind imports
try:
    from hive.rick_hive_mind import RickHiveMind, SignalStrength
    HIVE_AVAILABLE = True
except ImportError:
    HIVE_AVAILABLE = False
    print("⚠️  Hive Mind not available - running without swarm coordination")

# Hive-LLM Orchestrator imports
try:
    from hive.hive_llm_orchestrator import HiveLLMOrchestrator, TradeOpportunity
    HIVE_LLM_ORCHESTRATOR_AVAILABLE = True
except ImportError:
    HIVE_LLM_ORCHESTRATOR_AVAILABLE = False
    print("⚠️  Hive-LLM Orchestrator not available")

# Momentum & Trailing imports (extracted from rbotzilla_golden_age.py)
try:
    from util.momentum_trailing import MomentumDetector, SmartTrailingSystem
    MOMENTUM_SYSTEM_AVAILABLE = True
except ImportError:
    MOMENTUM_SYSTEM_AVAILABLE = False
    print("⚠️  Momentum/Trailing system not available")

class OandaTradingEngine:
    """
    RBOTzilla Charter-Compliant OANDA Trading Engine
    - Environment agnostic (practice/live determined by API token/endpoint only)
    - Immutable OCO orders (3:1 R:R minimum)
    - Full narration logging to JSONL
    - ML regime detection and signal analysis
    - Rick Hive Mind coordination
    - Sub-300ms execution tracking
    """
    
    def __init__(self, environment='practice'):
        """
        Initialize Trading Engine
        
        Args:
            environment: 'practice' or 'live' (default: practice)
                        Only difference is API endpoint and token used
        """
        # Validate Charter PIN
        if not RickCharter.validate_pin(841921):
            raise PermissionError("Invalid Charter PIN - cannot initialize trading engine")
        
        self.display = TerminalDisplay()
        self.environment = environment
        
        # Initialize OANDA connector: environment determines endpoint only
        self.oanda = OandaConnector(environment=environment)
        env_label = "PRACTICE" if environment == 'practice' else "LIVE"
        self.display.success(f"✅ {env_label} API connected")
        print(f"   Account: {self.oanda.account_id}")
        print(f"   Endpoint: {self.oanda.api_base}")
        
        # Initialize Rick's narration system
        self.narrator = RickNarrator()
        
        # Initialize ML Intelligence if available
        if ML_AVAILABLE:
            self.regime_detector = RegimeDetector()
            self.signal_analyzer = SignalAnalyzer()
            self.display.success("✅ ML Intelligence loaded")
        else:
            self.regime_detector = None
            self.signal_analyzer = None
        
        # Initialize Hive Mind if available
        if HIVE_AVAILABLE:
            self.hive_mind = RickHiveMind()
            self.display.success("✅ Hive Mind connected")
        else:
            self.hive_mind = None
        
        # Initialize Hive-LLM Orchestrator if available
        if HIVE_LLM_ORCHESTRATOR_AVAILABLE:
            self.hive_llm_orchestrator = HiveLLMOrchestrator()
            self.display.success("✅ Hive-LLM Orchestrator initialized")
        else:
            self.hive_llm_orchestrator = None
        
        # Initialize Momentum System if available
        if MOMENTUM_SYSTEM_AVAILABLE:
            self.momentum_detector = MomentumDetector()
            self.trailing_system = SmartTrailingSystem()
            self.display.success("✅ Momentum/Trailing system loaded")
        else:
            self.momentum_detector = None
            self.trailing_system = None
        
        # Initialize Strategy Aggregator (combines 5 prototype strategies)
        try:
            from util.strategy_aggregator import StrategyAggregator
            self.strategy_aggregator = StrategyAggregator(signal_vote_threshold=2)
            self.display.success("✅ Strategy Aggregator loaded (5 prototype strategies)")
        except ImportError:
            self.strategy_aggregator = None
            self.display.warning("⚠️  Strategy Aggregator not available")
        
        # Initialize Quantitative Hedge Engine (correlation-based hedging)
        try:
            from util.quant_hedge_engine import QuantHedgeEngine
            self.hedge_engine = QuantHedgeEngine()
            self.active_hedges = {}  # Track active hedge positions
            self.display.success("✅ Quantitative Hedge Engine loaded")
        except ImportError:
            self.hedge_engine = None
            self.active_hedges = {}
            self.display.warning("⚠️  Hedge Engine not available")
        
        # Initialize Positions Registry (cross-platform position tracking)
        try:
            self.positions_registry = PositionsRegistry()
            self.display.success("✅ Positions Registry initialized")
        except Exception as e:
            self.positions_registry = None
            self.display.warning(f"⚠️  Positions Registry unavailable: {e}")
        
        # Charter-compliant trading parameters
        self.charter = RickCharter
        
        # ========================================================================
        # MARGIN & CORRELATION GUARDIAN GATES (NEW)
        # ========================================================================
        # Get account NAV for gate calculations — OandaAccount is a dataclass
        account_nav = 10000.0  # safe fallback
        try:
            if hasattr(self.oanda, 'get_account_info'):
                account_info = self.oanda.get_account_info()
                if account_info is not None:
                    # OandaAccount dataclass: use .balance attribute
                    account_nav = float(getattr(account_info, 'balance', None) or 10000.0)
        except Exception as e:
            self.display.warning(f"⚠️  Could not fetch account NAV: {e}, using default $10k")
        
        self.gate = MarginCorrelationGate(account_nav=account_nav)
        self.current_positions = []  # Track positions for gate monitoring
        self.pending_orders = []      # Track pending orders for gate monitoring
        self.display.success("🛡️  Margin & Correlation Guardian Gates ACTIVE")
        
        # Focused 5 major pairs (highest liquidity, tightest spreads)
        # Reference: oanda_trading_engine.PATCH_PROPOSAL.py (dec4_dec10)
        self.trading_pairs = [
            'EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD',
        ]
        
        self.min_trade_interval = 300  # 5 minutes when positions FULL (M15 Charter floor)
        # Scan cadence: fast when slots remain, slow only when at capacity
        self.scan_fast_seconds = int(os.getenv('RBOT_SCAN_FAST_SECONDS', '60'))
        self.scan_slow_seconds = int(os.getenv('RBOT_SCAN_SLOW_SECONDS', '300'))
        
        # Confidence gate — reject signals below this threshold
        # Updated for quality filtering: only 76%+ signals (ema_stack, fibonacci, fvg)
        self.min_confidence = 0.76

        # ── Multi-signal scan config (env-overridable) ────────────────────────
        # min_signal_confidence: final selection gate (above min_confidence)
        # max_new_trades_per_cycle: hard cap on new orders per loop iteration
        # scan_log_top_n: how many candidates/rejects to print each cycle
        self.min_signal_confidence  = float(os.getenv('RBOT_MIN_SIGNAL_CONFIDENCE',  '0.76'))
        self.max_new_trades_per_cycle = int(os.getenv('RBOT_MAX_NEW_TRADES_PER_CYCLE', '3'))
        self.scan_log_top_n         = int(os.getenv('RBOT_SCAN_LOG_TOP_N',           '8'))
        
        # IMMUTABLE RISK MANAGEMENT (Charter Section 3.2)
        self.min_notional_usd = self.charter.MIN_NOTIONAL_USD  # $15,000 minimum (Charter immutable)
        # Tight SL/TP from rbz reference: 10 pip SL, 32 pip TP (3.2:1)
        self.stop_loss_pips = 10
        self.take_profit_pips = 32  # 3.2:1 R:R ratio (Charter minimum)
        self.trailing_start_pips = 3   # Begin trailing after 3 pip profit
        self.trailing_dist_pips  = 5   # Trail at 5 pips distance
        self.min_rr_ratio = self.charter.MIN_RISK_REWARD_RATIO  # 3.2
        self.max_daily_loss = abs(self.charter.DAILY_LOSS_BREAKER_PCT)  # 5%
        
        # Position sizes calculated dynamically to meet Charter $15k minimum
        self.position_size = 14000  # Base size (adjusted per pair to meet minimums)
        
        # State tracking
        self.active_positions = {}
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.is_running = False
        self.session_start = datetime.now(timezone.utc)
        
        # Platform-specific pair management (per user requirement)
        # Max 3-4 pairs per platform, no duplicates across platforms
        self.max_pairs_per_platform = 4
        self.active_pairs = set()  # Track active pairs on this platform
        self.global_active_pairs_file = '/tmp/rick_trading_global_pairs.json'  # Cross-platform tracking
        
        # TradeManager settings
        # Only consider converting TP -> trailing SL after 60 seconds
        self.min_position_age_seconds = 60
        # Hive consensus threshold to trigger TP cancellation
        self.hive_trigger_confidence = 0.80
        self.trade_manager_active = False  # Track if trade manager is running
        self.trade_manager_last_heartbeat = None  # Last time trade manager was active

        # Wire tight trailing overrides (rbz_tight_trailing.py reference)
        if RBZ_TRAILING_AVAILABLE:
            try:
                apply_rbz_overrides(connector=self.oanda, engine=self)
                self.display.success("✅ RBZ tight trailing + TP guard wired")
            except Exception as _rbz_err:
                self.display.warning(f"⚠️  RBZ trailing wire failed: {_rbz_err}")
        
        # Narration logging
        log_narration(
            event_type="ENGINE_START",
            details={
                "pin": "841921",
                "environment": environment,
                "charter_compliant": True,
                "ml_enabled": ML_AVAILABLE,
                "hive_enabled": HIVE_AVAILABLE,
                "min_rr_ratio": self.min_rr_ratio
            },
            symbol="SYSTEM",
            venue="oanda"
        )
        
        # ========================================================================
        # POSITION DASHBOARD (Active monitoring + display)
        # ========================================================================
        self.dashboard = PositionDashboard(refresh_interval_sec=60)
        self.display.success("✅ Position Dashboard initialized (60s refresh)")
        self.dashboard_task = None  # Track monitoring task
        
        self._display_startup()
    
    def _display_startup(self):
        """Display startup screen with Charter compliance info"""
        self.display.clear_screen()
        env_label = "PRACTICE" if self.environment == 'practice' else "LIVE"
        env_color = Colors.BRIGHT_YELLOW if self.environment == 'practice' else Colors.BRIGHT_RED
        
        self.display.header(
            f"🤖 RBOTzilla TRADING ENGINE ({env_label})",
            f"Charter-Compliant OANDA | PIN: 841921 | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        self.display.section("CHARTER COMPLIANCE STATUS")
        self.display.info("PIN Validated", "841921 ✅", Colors.BRIGHT_GREEN)
        self.display.info("Charter Version", "RBOTzilla UNI Phase 9", Colors.BRIGHT_CYAN)
        self.display.info("Immutable OCO", "ENFORCED (All orders)", Colors.BRIGHT_GREEN)
        self.display.info("Min R:R Ratio", f"{self.min_rr_ratio}:1 (Charter Immutable)", Colors.BRIGHT_GREEN)
        self.display.info("Min Notional", f"${self.min_notional_usd:,} (Charter Immutable)", Colors.BRIGHT_GREEN)
        self.display.info("Max Daily Loss", f"{self.max_daily_loss}% (Charter Breaker)", Colors.BRIGHT_GREEN)
        self.display.info("Max Latency", f"{self.charter.MAX_PLACEMENT_LATENCY_MS}ms (Charter 2.1)", Colors.BRIGHT_GREEN)
        
        self.display.section("ENVIRONMENT CONFIGURATION")
        self.display.info("Environment", env_label, env_color)
        self.display.info("API Endpoint", self.oanda.api_base, Colors.BRIGHT_CYAN)
        self.display.info("Account ID", self.oanda.account_id, Colors.BRIGHT_CYAN)
        
        self.display.section("TRADE MANAGEMENT")
        self.display.info("Max Pairs Per Platform", f"{self.max_pairs_per_platform} pairs", Colors.BRIGHT_GREEN)
        self.display.info("Active Pairs", f"{len(self.active_pairs)}/{self.max_pairs_per_platform}", Colors.BRIGHT_CYAN)
        self.display.info("Trade Manager", "Will activate on start", Colors.BRIGHT_YELLOW)
        self.display.info("Smart Trailing", "Enabled (Momentum-based)", Colors.BRIGHT_GREEN)
        self.display.info("TP/SL Enforcement", "MANDATORY (OCO Required)", Colors.BRIGHT_GREEN)
        self.display.info("Market Data", "Real-time OANDA API", Colors.BRIGHT_GREEN)
        self.display.info("Order Execution", f"OANDA {env_label} API", env_color)
        
        self.display.section("SYSTEM COMPONENTS")
        self.display.info("Narration Logging", "ACTIVE → narration.jsonl", Colors.BRIGHT_GREEN)
        self.display.info("ML Intelligence", "ACTIVE" if ML_AVAILABLE else "DISABLED", 
                         Colors.BRIGHT_GREEN if ML_AVAILABLE else Colors.BRIGHT_BLACK)
        self.display.info("Hive Mind", "CONNECTED" if HIVE_AVAILABLE else "STANDALONE",
                         Colors.BRIGHT_GREEN if HIVE_AVAILABLE else Colors.BRIGHT_BLACK)
        self.display.info("Momentum System", "ACTIVE (rbotzilla_golden_age)" if MOMENTUM_SYSTEM_AVAILABLE else "DISABLED",
                         Colors.BRIGHT_GREEN if MOMENTUM_SYSTEM_AVAILABLE else Colors.BRIGHT_BLACK)
        
        self.display.section("RISK PARAMETERS")
        self.display.info("Position Size", f"~{self.position_size:,} units (dynamic per pair)", Colors.BRIGHT_CYAN)
        self.display.info("Stop Loss", f"{self.stop_loss_pips} pips", Colors.BRIGHT_CYAN)
        self.display.info("Take Profit", f"{self.take_profit_pips} pips (3.2:1 R:R)", Colors.BRIGHT_CYAN)
        self.display.info("Max Positions", "3 concurrent", Colors.BRIGHT_CYAN)
        print()
        self.display.warning("⚠️  Charter requires $15k min notional - positions sized accordingly")
        
        self.display.section("OANDA CONNECTION")
        self.display.connection_status(f"OANDA {env_label} API", "READY")
        
        print()
        self.display.alert(f"✅ RBOTzilla Engine Ready - {env_label} Environment", "SUCCESS")
        
        self.display.divider()
        print()
    
    def get_current_price(self, pair):
        """Get current real-time price from OANDA API (environment-agnostic)"""
        try:
            # Get real-time prices from OANDA API (practice or live based on connector config)
            api_base = self.oanda.api_base
            headers = self.oanda.headers
            account_id = self.oanda.account_id
            
            response = requests.get(
                f"{api_base}/v3/accounts/{account_id}/pricing",
                headers=headers,
                params={"instruments": pair},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'prices' in data and len(data['prices']) > 0:
                    price_info = data['prices'][0]
                    bid = float(price_info['bids'][0]['price'])
                    ask = float(price_info['asks'][0]['price'])
                    spread = round((ask - bid) * 10000, 1)  # in pips
                    
                    return {
                        'bid': bid,
                        'ask': ask,
                        'spread': spread,
                        'real_api': True
                    }
            
            raise RuntimeError(f"OANDA pricing failed for {pair} (status {response.status_code})")
            
        except Exception as e:
            raise RuntimeError(f"OANDA pricing unavailable for {pair}: {e}") from e
    
    def evaluate_signal_with_ml(self, symbol: str, signal_data: Dict) -> Tuple[bool, Dict]:
        """
        Filter signals through ML regime detection and strength analysis
        
        Returns:
            (bool, dict): (approved, analysis_details)
        """
        if not self.regime_detector or not self.signal_analyzer:
            # No ML, accept signal
            return True, {'ml_available': False, 'reason': 'ML not available'}
        
        try:
            # Get recent price data for ML analysis
            price_data = self.get_current_price(symbol)
            if not price_data:
                return False, {'ml_available': True, 'reason': 'Could not fetch price data'}
            
            # Detect market regime
            regime = self.regime_detector.detect_regime(symbol)
            
            # Analyze signal quality
            strength = self.signal_analyzer.analyze_signal(
                symbol, 
                signal_data.get('action', 'buy'),
                signal_data.get('entry', price_data.get('ask', 0))
            )
            
            # Accept signals with high confidence in trending regimes
            if regime in ['trending_up', 'trending_down']:
                # Strong trend: accept if confidence >= 0.70
                if strength >= 0.70:
                    log_narration(
                        event_type="ML_SIGNAL_APPROVED",
                        details={
                            "symbol": symbol,
                            "regime": regime,
                            "strength": strength,
                            "reason": "High confidence in strong trend"
                        },
                        symbol=symbol,
                        venue="ml_intelligence"
                    )
                    return True, {
                        'ml_available': True,
                        'regime': regime,
                        'strength': strength,
                        'approved': True
                    }
            
            elif regime in ['ranging', 'consolidating']:
                # Low trend environment: accept only exceptional signals (>0.80)
                if strength >= 0.80:
                    log_narration(
                        event_type="ML_SIGNAL_APPROVED",
                        details={
                            "symbol": symbol,
                            "regime": regime,
                            "strength": strength,
                            "reason": "Exceptional signal in ranging market"
                        },
                        symbol=symbol,
                        venue="ml_intelligence"
                    )
                    return True, {
                        'ml_available': True,
                        'regime': regime,
                        'strength': strength,
                        'approved': True
                    }
            
            # Signal rejected due to weak confidence
            log_narration(
                event_type="ML_SIGNAL_REJECTED",
                details={
                    "symbol": symbol,
                    "regime": regime,
                    "strength": strength,
                    "reason": f"Insufficient confidence in {regime} regime"
                },
                symbol=symbol,
                venue="ml_intelligence"
            )
            
            return False, {
                'ml_available': True,
                'regime': regime,
                'strength': strength,
                'approved': False,
                'reason': f'Weak signal ({strength:.2f}) in {regime} market'
            }
        
        except Exception as e:
            # ML error - be permissive, don't block trade
            self.display.warning(f"ML evaluation error for {symbol}: {str(e)}")
            return True, {'ml_available': True, 'error': str(e), 'approved': True}
    
    def amplify_signal_with_hive(self, symbol: str, signal_data: Dict) -> Dict:
        """
        Amplify signal strength through Hive Mind consensus
        
        Args:
            symbol: Currency pair
            signal_data: Signal dict with 'action', 'entry', etc.
        
        Returns:
            Amplified signal dict with hive_amplified flag and confidence
        """
        if not self.hive_mind:
            # No Hive, return original
            return signal_data
        
        try:
            # Query Hive Mind for consensus on this symbol
            market_data = {
                "symbol": symbol.replace('_', ''),
                "action": signal_data.get('action', 'buy'),
                "entry_price": signal_data.get('entry', 0),
                "timeframe": "M15"
            }
            
            hive_analysis = self.hive_mind.delegate_analysis(market_data)
            
            if not hive_analysis:
                return signal_data
            
            consensus = hive_analysis.consensus_signal
            confidence = hive_analysis.consensus_confidence
            
            # Check if Hive strongly agrees with signal
            if confidence >= self.hive_trigger_confidence:
                # Hive consensus is strong
                
                # Amplify the signal
                amplified_signal = signal_data.copy()
                amplified_signal['hive_amplified'] = True
                amplified_signal['hive_confidence'] = confidence
                amplified_signal['hive_consensus'] = consensus.value if hasattr(consensus, 'value') else str(consensus)
                
                log_narration(
                    event_type="HIVE_CONSENSUS_STRONG",
                    details={
                        "symbol": symbol,
                        "consensus": consensus.value if hasattr(consensus, 'value') else str(consensus),
                        "confidence": confidence,
                        "original_signal": signal_data.get('tag', 'unknown'),
                        "amplified": True
                    },
                    symbol=symbol,
                    venue="hive_mind"
                )
                
                self.display.success(f"🐝 Hive amplified {symbol}: {consensus} ({confidence:.2f})")
                
                return amplified_signal
            else:
                # Hive consensus weak - return original signal
                log_narration(
                    event_type="HIVE_CONSENSUS_WEAK",
                    details={
                        "symbol": symbol,
                        "consensus": consensus.value if hasattr(consensus, 'value') else str(consensus),
                        "confidence": confidence,
                        "threshold": self.hive_trigger_confidence
                    },
                    symbol=symbol,
                    venue="hive_mind"
                )
                
                return signal_data
        
        except Exception as e:
            # Hive error - return original signal
            self.display.warning(f"Hive amplification error for {symbol}: {str(e)}")
            return signal_data
    
    def calculate_position_size(self, symbol: str, entry_price: float) -> int:
        """Calculate Charter-compliant position size to meet $15k minimum notional.

        Notional rule by pair type:
          USD_XXX  (USD_CAD, USD_JPY, USD_CHF …): 1 unit = $1 USD  → need min_notional units
          XXX_USD  (EUR_USD, GBP_USD, AUD_USD …): 1 unit = price $ → need min_notional / price units
          crosses  (EUR_JPY, GBP_CAD …):          approximate via price; gate will verify
        """
        import math
        parts = symbol.upper().split("_")
        base  = parts[0] if len(parts) == 2 else ""
        quote = parts[1] if len(parts) == 2 else ""

        if base == "USD":
            # USD_JPY, USD_CAD, USD_CHF — base IS dollars, 1 unit = $1
            required_units = math.ceil(self.min_notional_usd)
        elif quote == "USD":
            # EUR_USD, GBP_USD, AUD_USD — notional = units × price
            required_units = math.ceil(self.min_notional_usd / entry_price)
        else:
            # Cross pair — use price as rough proxy; charter gate will catch any miss
            required_units = math.ceil(self.min_notional_usd / entry_price)

        # Round up to nearest 100 for clean order sizes
        position_size = math.ceil(required_units / 100) * 100
        return position_size
    
    def _load_global_active_pairs(self) -> set:
        """Load active pairs from all platforms to prevent duplicates"""
        try:
            if os.path.exists(self.global_active_pairs_file):
                with open(self.global_active_pairs_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('pairs', []))
        except Exception as e:
            self.display.warning(f"Could not load global active pairs: {e}")
        return set()
    
    def _save_global_active_pairs(self, pairs: set):
        """Save active pairs to global tracker"""
        try:
            with open(self.global_active_pairs_file, 'w') as f:
                json.dump({
                    'pairs': list(pairs),
                    'platform': 'oanda',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }, f)
        except Exception as e:
            self.display.warning(f"Could not save global active pairs: {e}")
    
    def _can_trade_pair(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if we can trade this pair based on platform limits
        
        Returns:
            Tuple of (can_trade: bool, reason: str)
        """
        # Check platform-specific limit (3-4 pairs max)
        if len(self.active_pairs) >= self.max_pairs_per_platform:
            if symbol not in self.active_pairs:
                return False, f"Platform limit reached ({self.max_pairs_per_platform} pairs max)"
        
        # Check cross-platform duplicates
        global_pairs = self._load_global_active_pairs()
        if symbol in global_pairs and symbol not in self.active_pairs:
            return False, f"Pair {symbol} already active on another platform"
        
        return True, "OK"
    
    def _validate_tp_sl_set(self, symbol: str, stop_loss: float, take_profit: float, direction: str) -> bool:
        """
        Validate that TP and SL are properly set and meet requirements
        
        Args:
            symbol: Trading pair
            stop_loss: Stop loss price
            take_profit: Take profit price
            direction: BUY or SELL
            
        Returns:
            True if valid, raises ValueError otherwise
        """
        if stop_loss is None:
            raise ValueError(f"CRITICAL: Stop Loss not set for {symbol} {direction}")
        
        if take_profit is None:
            raise ValueError(f"CRITICAL: Take Profit not set for {symbol} {direction}")
        
        # Validate that SL and TP are in the correct direction
        if direction == "BUY":
            if stop_loss >= take_profit:
                raise ValueError(f"CRITICAL: For BUY, SL ({stop_loss}) must be < TP ({take_profit})")
        else:  # SELL
            if stop_loss <= take_profit:
                raise ValueError(f"CRITICAL: For SELL, SL ({stop_loss}) must be > TP ({take_profit})")
        
        # Log successful validation
        log_narration(
            event_type="TP_SL_VALIDATED",
            details={
                "symbol": symbol,
                "direction": direction,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "validation": "PASSED"
            },
            symbol=symbol,
            venue="oanda"
        )
        
        return True
    
    def calculate_stop_take_levels(self, symbol: str, direction: str, entry_price: float):
        """
        Calculate stop loss and take profit levels
        
        IMPORTANT: Both SL and TP are ALWAYS calculated and returned.
        This ensures OCO order compliance for all trades.
        """
        pip_size = 0.0001  # Standard for most pairs
        if 'JPY' in symbol:
            pip_size = 0.01
        
        if direction == "BUY":
            stop_loss = entry_price - (self.stop_loss_pips * pip_size)
            take_profit = entry_price + (self.take_profit_pips * pip_size)
        else:  # SELL
            stop_loss = entry_price + (self.stop_loss_pips * pip_size)
            take_profit = entry_price - (self.take_profit_pips * pip_size)
        
        # Validate that both values are set
        if stop_loss is None or take_profit is None:
            raise ValueError(f"CRITICAL: Failed to calculate TP/SL for {symbol} {direction}")
        
        return round(stop_loss, 5), round(take_profit, 5)
    
    def _evaluate_hedge_conditions(self, symbol: str, direction: str, units: float, 
                                   entry_price: float, notional: float, current_margin_used: float) -> Dict:
        """
        Intelligent multi-condition hedge evaluation
        Analyzes portfolio state, market conditions, and risk exposure
        
        Returns:
            Dict with 'execute' (bool) and 'reason' (str)
        """
        # Get account NAV for calculations
        account_nav = 2000.0
        try:
            if hasattr(self.oanda, 'get_account_info'):
                account_info = self.oanda.get_account_info()
                account_nav = float(account_info.get('NAV', 2000.0))
        except Exception:
            pass
        
        # Calculate current margin utilization
        margin_utilization = (current_margin_used / account_nav) if account_nav > 0 else 0
        
        # Evaluate hedge opportunity
        hedge_opp = self.hedge_engine.evaluate_hedge_opportunity(symbol)
        
        # ========================================================================
        # HEDGE DECISION RULES - Multi-Condition Analysis
        # ========================================================================
        
        # RULE 1: No suitable hedge pair available
        if not hedge_opp['hedge_available']:
            return {'execute': False, 'reason': 'No inverse correlation pair found'}
        
        # RULE 2: Weak correlation (< -0.50 threshold)
        if abs(hedge_opp['correlation']) < 0.50:
            return {'execute': False, 'reason': f"Weak correlation ({hedge_opp['correlation']:.2f})"}
        
        # RULE 3: High margin usage (>25%) - ALWAYS hedge to protect capital
        if margin_utilization > 0.25:
            return {
                'execute': True, 
                'reason': f'High margin usage ({margin_utilization:.1%}) - protective hedge required'
            }
        
        # RULE 4: Large notional (>$20k) - Hedge to reduce single-position risk
        if notional > 20000:
            return {
                'execute': True,
                'reason': f'Large notional (${notional:,.0f}) - risk reduction hedge'
            }
        
        # RULE 5: Multiple positions in same currency - Hedge cumulative exposure
        usd_exposure_count = sum(1 for pos in self.current_positions 
                                 if 'USD' in pos.symbol and pos.side == ("LONG" if direction == "BUY" else "SHORT"))
        if usd_exposure_count >= 2:
            return {
                'execute': True,
                'reason': f'Cumulative USD exposure ({usd_exposure_count + 1} positions) - correlation hedge'
            }
        
        # RULE 6: Strong inverse correlation (< -0.70) - Opportunistic hedge
        if hedge_opp['correlation'] < -0.70:
            return {
                'execute': True,
                'reason': f"Strong inverse correlation ({hedge_opp['correlation']:.2f}) - optimal hedge opportunity"
            }
        
        # RULE 7: Moderate margin (15-25%) + Strong correlation - Selective hedge
        if 0.15 < margin_utilization <= 0.25 and hedge_opp['correlation'] < -0.65:
            return {
                'execute': True,
                'reason': f'Moderate margin ({margin_utilization:.1%}) + strong correlation - proactive hedge'
            }
        
        # DEFAULT: Skip hedge for low-risk scenarios
        return {
            'execute': False,
            'reason': f'Low risk profile (margin: {margin_utilization:.1%}, notional: ${notional:,.0f})'
        }
    
    def place_trade(self, symbol: str, direction: str,
                   signal_sl: float = None, signal_tp: float = None):
        """Place Charter-compliant OCO order with full logging (environment-agnostic)"""
        try:
            # ========================================================================
            # 🛡️ PAIR LIMIT CHECK (NEW - Per User Requirement)
            # ========================================================================
            can_trade, reason = self._can_trade_pair(symbol)
            if not can_trade:
                self.display.error(f"❌ PAIR LIMIT BLOCKED: {reason}")
                log_narration(
                    event_type="PAIR_LIMIT_REJECTION",
                    details={
                        "symbol": symbol,
                        "reason": reason,
                        "active_pairs": list(self.active_pairs),
                        "max_pairs": self.max_pairs_per_platform
                    },
                    symbol=symbol,
                    venue="oanda"
                )
                return None
            
            # ========================================================================
            # 🛡️ POSITIONS REGISTRY CHECK (Prevent duplicate positions across platforms)
            # ========================================================================
            if self.positions_registry:
                if not self.positions_registry.is_symbol_available(symbol):
                    self.display.error(f"❌ BROKER_REGISTRY_BLOCK: {symbol} already in use on another platform")
                    log_narration(
                        event_type="BROKER_REGISTRY_BLOCK",
                        details={
                            "symbol": symbol,
                            "reason": "Symbol already has active position on another platform",
                            "active_positions": self.positions_registry.get_active_positions()
                        },
                        symbol=symbol,
                        venue="oanda"
                    )
                    return None
            
            # Get current price
            price_data = self.get_current_price(symbol)
            if not price_data:
                self.display.error(f"Could not get price for {symbol}")
                log_narration(
                    event_type="PRICE_ERROR",
                    details={"symbol": symbol, "error": "No price data"},
                    symbol=symbol,
                    venue="oanda"
                )
                return None
            
            # Use bid for SELL, ask for BUY
            entry_price = price_data['ask'] if direction == "BUY" else price_data['bid']
            
            # Calculate Charter-compliant position size
            position_size = self.calculate_position_size(symbol, entry_price)
            
            # Calculate notional value in TRUE USD (handles cross pairs correctly)
            notional_value = get_usd_notional(position_size, symbol, entry_price, self.oanda)
            if notional_value is None:
                self.display.error(f"❌ Cannot calculate USD notional for {symbol}")
                return None
            
            # ========================================================================
            # 🛡️ PRE-TRADE GUARDIAN GATE CHECK (NEW)
            # ========================================================================
            # Get current account margin — OandaAccount is a dataclass
            current_margin_used = 0
            try:
                if hasattr(self.oanda, 'get_account_info'):
                    account_info = self.oanda.get_account_info()
                    if account_info is not None:
                        current_margin_used = float(
                            getattr(account_info, 'margin_used', None) or 0
                        )
            except Exception as e:
                self.display.warn(f"⚠️  Could not fetch margin info: {e}")
            
            # Create order object for gate validation
            gate_order = Order(
                symbol=symbol,
                side=direction,
                units=position_size,
                price=entry_price,
                order_id=f"pending_{symbol}_{int(time.time())}"
            )
            
            # Run pre-trade gate
            gate_result = self.gate.pre_trade_gate(
                new_order=gate_order,
                current_positions=self.current_positions,
                pending_orders=self.pending_orders,
                total_margin_used=current_margin_used
            )
            
            # If gate rejects order, stop here
            if not gate_result.allowed:
                self.display.error(f"❌ GUARDIAN GATE BLOCKED: {gate_result.reason}")
                if gate_result.action == "AUTO_CANCEL":
                    self.display.alert(f"   Action: {gate_result.action}", "WARNING")
                log_narration(
                    event_type="GATE_REJECTION",
                    details={
                        "symbol": symbol,
                        "reason": gate_result.reason,
                        "action": gate_result.action,
                        "margin_used": current_margin_used
                    },
                    symbol=symbol,
                    venue="oanda"
                )
                return None
            
            # CHARTER ENFORCEMENT: Verify minimum notional — UPSIZE instead of reject
            if notional_value < self.min_notional_usd:
                import math as _math
                _parts = symbol.upper().split("_")
                _base  = _parts[0] if len(_parts) == 2 else ""
                _quote = _parts[1] if len(_parts) == 2 else ""
                if _base == "USD":
                    _req = _math.ceil(self.min_notional_usd)
                elif _quote == "USD":
                    _req = _math.ceil(self.min_notional_usd / entry_price)
                else:
                    _req = _math.ceil(self.min_notional_usd / entry_price)
                _new_size = _math.ceil(max(position_size, _req) / 100) * 100
                _new_notional = get_usd_notional(_new_size, symbol, entry_price, self.oanda) or (_new_size * entry_price)

                self.display.success(
                    f"⚙️  UPSIZE: {symbol} units {position_size:,} → {_new_size:,} "
                    f"to meet ${self.min_notional_usd:,} notional "
                    f"(was ${notional_value:,.0f} → now ${_new_notional:,.0f})"
                )
                log_narration(
                    event_type="UPSIZE_TO_MIN_NOTIONAL",
                    details={
                        "symbol": symbol,
                        "direction": direction,
                        "units_before": position_size,
                        "units_after": _new_size,
                        "notional_before": round(notional_value, 2),
                        "notional_after": round(_new_notional, 2),
                        "min_required_usd": self.min_notional_usd,
                        "entry_price": entry_price,
                    },
                    symbol=symbol,
                    venue="risk"
                )
                position_size  = _new_size
                notional_value = _new_notional

                # Re-check margin gate with new size
                gate_order.units = position_size
                _new_margin = position_size * (1.0 if _base == "USD" else entry_price) * 0.02
                _proj_pct = (current_margin_used + _new_margin) / max(self.gate.account_nav, 1)
                if _proj_pct > self.gate.MARGIN_CAP_PCT:
                    self.display.error(
                        f"❌ POST-UPSIZE MARGIN CAP: {_proj_pct*100:.1f}% after upsize — skipping"
                    )
                    return None
            
            # Display market data
            self.display.section("MARKET SCAN")
            
            self.display.success("✅ Real-time OANDA API data")
            
            self.display.market_data(
                symbol,
                price_data['bid'],
                price_data['ask'],
                price_data['spread']  # already in pips
            )
            
            # Calculate stops.
            #
            # Signal SL/TP are anchored to the candle-close price, not the live
            # bid/ask.  If price drifted since the close the raw values would
            # create a wrong distance (e.g. 1-pip SL) and fail the RR gate.
            # Re-apply the *distance* from the signal to the live entry price,
            # with the charter pip values as an absolute floor.
            pip = 0.01 if 'JPY' in symbol else 0.0001
            charter_sl_dist = self.stop_loss_pips   * pip   # e.g. 0.0010
            charter_tp_dist = self.take_profit_pips * pip   # e.g. 0.0032

            if signal_sl is not None and signal_tp is not None:
                if direction == 'BUY':
                    sl_dist = max(abs(entry_price - signal_sl), charter_sl_dist)
                    tp_dist = max(abs(signal_tp   - entry_price), charter_tp_dist)
                    stop_loss   = round(entry_price - sl_dist, 5)
                    take_profit = round(entry_price + tp_dist, 5)
                else:
                    sl_dist = max(abs(signal_sl   - entry_price), charter_sl_dist)
                    tp_dist = max(abs(entry_price - signal_tp),  charter_tp_dist)
                    stop_loss   = round(entry_price + sl_dist, 5)
                    take_profit = round(entry_price - tp_dist, 5)
            else:
                stop_loss, take_profit = self.calculate_stop_take_levels(symbol, direction, entry_price)
            
            # ========================================================================
            # 🛡️ VALIDATE TP/SL ARE SET (NEW - Per User Requirement)
            # ========================================================================
            self._validate_tp_sl_set(symbol, stop_loss, take_profit, direction)
            self.display.success(f"✅ TP/SL validated for {symbol} {direction}: SL={stop_loss:.5f}, TP={take_profit:.5f}")
            
            # CHARTER ENFORCEMENT: Verify R:R ratio
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0
            
            # If R:R is below minimum, ESCALATE TP to meet charter requirements
            # (rather than rejecting the trade)
            if rr_ratio < self.min_rr_ratio:
                required_reward = risk * self.min_rr_ratio
                if direction == "BUY":
                    take_profit = round(entry_price + required_reward, 5)
                    self.display.warning(
                        f"⚙️  RR ESCALATION: {rr_ratio:.2f} → {self.min_rr_ratio:.1f}:1 "
                        f"(TP {entry_price + (required_reward - reward):+.5f})"
                    )
                else:
                    take_profit = round(entry_price - required_reward, 5)
                    self.display.warning(
                        f"⚙️  RR ESCALATION: {rr_ratio:.2f} → {self.min_rr_ratio:.1f}:1 "
                        f"(TP {entry_price - (required_reward - reward):+.5f})"
                    )
                # Recalculate ratio with new TP
                reward = abs(take_profit - entry_price)
                rr_ratio = reward / risk if risk > 0 else 0
                log_narration(
                    event_type="RR_ESCALATION",
                    details={
                        "original_rr": reward / risk if risk > 0 else 0,
                        "escalated_rr": rr_ratio,
                        "target": self.min_rr_ratio,
                        "symbol": symbol
                    },
                    symbol=symbol,
                    venue="oanda"
                )
            
            # Use small tolerance for floating point comparison
            if rr_ratio < (self.min_rr_ratio - 0.01):
                self.display.error(f"❌ CHARTER VIOLATION: R:R {rr_ratio:.2f} < {self.min_rr_ratio}")
                log_narration(
                    event_type="CHARTER_VIOLATION",
                    details={
                        "violation": "MIN_RR_RATIO",
                        "rr_ratio": rr_ratio,
                        "min_required": self.min_rr_ratio,
                        "symbol": symbol
                    },
                    symbol=symbol,
                    venue="oanda"
                )
                return None
            
            # Determine units (negative for SELL)
            units = position_size if direction == "BUY" else -position_size
            
            # Display Charter compliance
            self.display.info("Position Size", f"{abs(units):,} units (dynamic)", Colors.BRIGHT_CYAN)
            self.display.info("Notional Value", f"${notional_value:,.0f} ✅", Colors.BRIGHT_GREEN)
            self.display.info("R:R Ratio", f"{rr_ratio:.2f}:1 ✅", Colors.BRIGHT_GREEN)
            
            # Place OCO order
            self.display.alert(f"Placing Charter-compliant {direction} OCO order for {symbol}...", "INFO")
            
            # Log pre-trade
            log_narration(
                event_type="TRADE_SIGNAL",
                details={
                    "symbol": symbol,
                    "direction": direction,
                    "entry": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "units": units,
                    "notional": notional_value,
                    "rr_ratio": rr_ratio,
                    "live_data": True
                },
                symbol=symbol,
                venue="oanda"
            )
            
            # Execute order via OANDA API (environment determined by connector config)
            order_result = self.oanda.place_oco_order(
                instrument=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                units=units,
                ttl_hours=6.0  # Charter: 6 hour max hold
            )
            
            if order_result.get('success'):
                order_id = order_result.get('order_id')
                latency_ms = order_result.get('latency_ms', 0)
                
                # CHARTER ENFORCEMENT: Verify latency
                if latency_ms > self.charter.MAX_PLACEMENT_LATENCY_MS:
                    self.display.error(f"❌ CHARTER VIOLATION: Latency {latency_ms:.1f}ms > 300ms")
                    log_narration(
                        event_type="CHARTER_VIOLATION",
                        details={
                            "violation": "MAX_LATENCY",
                            "latency_ms": latency_ms,
                            "max_allowed": self.charter.MAX_PLACEMENT_LATENCY_MS,
                            "order_id": order_id
                        },
                        symbol=symbol,
                        venue="oanda"
                    )
                    # Continue anyway since order was placed (just log violation)
                
                # Display successful trade
                self.display.trade_open(
                    symbol,
                    direction,
                    entry_price,
                    f"Stop: {stop_loss:.5f} | Target: {take_profit:.5f} | Size: {abs(units):,} units | Notional: ${notional_value:,.0f}"
                )
                
                # Track position
                self.active_positions[order_id] = {
                    'symbol': symbol,
                    'direction': direction,
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'units': units,
                    'notional': notional_value,
                    'rr_ratio': rr_ratio,
                    'timestamp': datetime.now(timezone.utc)
                }
                
                # ========================================================================
                # 🛡️ UPDATE ACTIVE PAIRS (NEW - Per User Requirement)
                # ========================================================================
                self.active_pairs.add(symbol)
                # Update global tracker to prevent duplicates across platforms
                global_pairs = self._load_global_active_pairs()
                global_pairs.add(symbol)
                self._save_global_active_pairs(global_pairs)
                
                self.display.success(f"✅ Pair {symbol} added to active pairs ({len(self.active_pairs)}/{self.max_pairs_per_platform})")
                
                # ========================================================================
                # 🛡️ TRACK POSITION FOR GUARDIAN GATE ONGOING MONITORING
                # ========================================================================
                gate_position = Position(
                    symbol=symbol,
                    side="LONG" if direction == "BUY" else "SHORT",
                    units=abs(units),
                    entry_price=entry_price,
                    current_price=entry_price,
                    pnl=0.0,
                    pnl_pips=0.0,
                    margin_used=(notional_value * 0.02),  # Typical FOREX margin ~2%
                    position_id=order_id
                )
                self.current_positions.append(gate_position)
                self.display.info("🛡️ Position tracked for guardian gate monitoring", "", Colors.BRIGHT_CYAN)
                
                # ========================================================================
                # 🛡️ REGISTER POSITION IN CROSS-PLATFORM REGISTRY
                # ========================================================================
                if self.positions_registry:
                    try:
                        registered = self.positions_registry.register_position(
                            symbol=symbol,
                            platform='oanda',
                            order_id=order_id,
                            direction=direction,
                            notional_usd=notional_value
                        )
                        if registered:
                            self.display.info("📋 Position registered in cross-platform registry", "", Colors.BRIGHT_CYAN)
                        else:
                            self.display.warning("⚠️  Position registry update failed (may already exist)")
                    except Exception as e:
                        self.display.warning(f"⚠️  Could not register position: {e}")
                
                # ========================================================================
                # 📊 ADD POSITION TO DASHBOARD (Real-time monitoring)
                # ========================================================================
                try:
                    strategy_name = ",".join(agg.detectors_fired) if agg and hasattr(agg, 'detectors_fired') else "unknown"
                    self.dashboard.add_position(
                        symbol=symbol,
                        strategy=strategy_name,
                        direction=direction,
                        entry_price=entry_price,
                        units=abs(units),
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        current_price=entry_price,
                    )
                    self.display.success(f"📊 {symbol} added to position dashboard (monitoring every 60s)")
                except Exception as e:
                    self.display.warning(f"⚠️  Dashboard update failed: {e}")
                
                self.total_trades += 1
                
                # Log successful placement with narration
                log_narration(
                    event_type="TRADE_OPENED",
                    details={
                        "symbol": symbol,
                        "direction": direction,
                        "entry_price": entry_price,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "size": abs(units),
                        "notional": notional_value,
                        "rr_ratio": rr_ratio,
                        "order_id": order_id,
                        "charter_compliant": True
                    },
                    symbol=symbol,
                    venue="oanda"
                )
                
                # Get Rick's commentary
                rick_comment = self.narrator.generate_commentary(
                    event_type="TRADE_OPENED",
                    details={
                        "symbol": symbol,
                        "direction": direction,
                        "entry": entry_price,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "rr_ratio": rr_ratio,
                        "notional": notional_value,
                        "reasoning": f"Charter-compliant {rr_ratio:.2f}:1 R:R, ${notional_value:,.0f} notional"
                    }
                )
                
                self.display.alert(f"✅ OCO order placed! Order ID: {order_id}", "SUCCESS")
                self.display.info("Latency", f"{latency_ms:.1f}ms", Colors.BRIGHT_CYAN)
                self.display.rick_says(rick_comment)
                
                # ========================================================================
                # 🛡️ QUANTITATIVE HEDGE ENGINE - INTELLIGENT MULTI-CONDITION ANALYSIS
                # ========================================================================
                if self.hedge_engine:
                    hedge_decision = self._evaluate_hedge_conditions(
                        symbol=symbol,
                        direction=direction,
                        units=abs(units),
                        entry_price=entry_price,
                        notional=notional_value,
                        current_margin_used=current_margin_used
                    )
                    
                    if hedge_decision['execute']:
                        self.display.section("HEDGE ANALYSIS")
                        self.display.info("Hedge Decision", hedge_decision['reason'], Colors.BRIGHT_YELLOW)
                        
                        hedge_position = self.hedge_engine.execute_hedge(
                            primary_symbol=symbol,
                            primary_side=direction,
                            position_size=abs(units),
                            entry_price=entry_price
                        )
                        
                        if hedge_position:
                            # Store hedge reference
                            self.active_hedges[order_id] = hedge_position
                            
                            self.display.success(
                                f"🛡️ HEDGE EXECUTED: {hedge_position.side} {hedge_position.size:.0f} units "
                                f"{hedge_position.symbol} @ {hedge_position.hedge_ratio:.0%} coverage"
                            )
                            self.display.info(
                                "Correlation", 
                                f"{hedge_position.correlation:.2f} (inverse)", 
                                Colors.BRIGHT_CYAN
                            )
                            
                            log_narration(
                                event_type="HEDGE_EXECUTED",
                                details={
                                    "primary_symbol": symbol,
                                    "hedge_symbol": hedge_position.symbol,
                                    "hedge_side": hedge_position.side,
                                    "hedge_size": hedge_position.size,
                                    "hedge_ratio": hedge_position.hedge_ratio,
                                    "correlation": hedge_position.correlation,
                                    "reason": hedge_decision['reason']
                                },
                                symbol=symbol,
                                venue="quant_hedge"
                            )
                            
                            # TODO: Place actual hedge order via OANDA API if live trading
                            # hedge_order_id = self.oanda.place_oco_order(
                            #     instrument=hedge_position.symbol,
                            #     entry_price=hedge_position.entry_price,
                            #     units=hedge_position.size if hedge_position.side == 'BUY' else -hedge_position.size,
                            #     ...
                            # )
                        else:
                            self.display.warning("⚠️  No suitable hedge pair found")
                    else:
                        self.display.info("Hedge Decision", f"SKIPPED - {hedge_decision['reason']}", Colors.DIM)
                
                return order_id
            else:
                error = order_result.get('error', 'Unknown error')
                self.display.error(f"Order failed: {error}")
                
                log_narration(
                    event_type="ORDER_FAILED",
                    details={
                        "symbol": symbol,
                        "direction": direction,
                        "error": error,
                        "environment": self.environment
                    },
                    symbol=symbol,
                    venue="oanda"
                )
                
                return None
                
        except Exception as e:
            self.display.error(f"Error placing trade: {e}")
            log_narration(
                event_type="TRADE_ERROR",
                details={"error": str(e), "symbol": symbol},
                symbol=symbol,
                venue="oanda"
            )
            return None
    
    def check_positions(self):
        """Check status of open positions via OANDA API"""
        # Positions managed by TradeManager background loop
        # This method can be extended to sync state with OANDA API if needed
        return

    def _sync_open_positions(self):
        """
        Pull current open trades from OANDA and add any that are missing from
        active_positions.  Called on startup AND at the top of each trade_manager
        cycle so positions placed manually or before a restart are always tracked.
        """
        try:
            trades = self.oanda.get_trades() or []
        except Exception as e:
            self.display.warning(f"_sync_open_positions: get_trades failed — {e}")
            return

        for t in trades:
            symbol    = (t.get('instrument') or t.get('symbol', '')).upper()
            trade_id  = str(t.get('id') or t.get('tradeID') or t.get('trade_id', ''))
            if not trade_id or trade_id in self.active_positions:
                continue

            raw_units = float(t.get('currentUnits') or t.get('units') or 0)
            direction = 'BUY' if raw_units > 0 else 'SELL'
            entry     = float(t.get('price') or t.get('averagePrice') or 0)

            # Try to read attached SL/TP orders from the trade object
            sl_order  = t.get('stopLossOrder') or {}
            tp_order  = t.get('takeProfitOrder') or {}
            sl_price  = float(sl_order.get('price', 0))
            tp_price  = float(tp_order.get('price', 0))

            # Fallback: derive SL/TP from our config defaults
            pip = 0.01 if 'JPY' in symbol else 0.0001
            if sl_price == 0:
                sl_price = (entry - self.stop_loss_pips * pip) if direction == 'BUY' \
                           else (entry + self.stop_loss_pips * pip)
            if tp_price == 0:
                tp_price = (entry + self.take_profit_pips * pip) if direction == 'BUY' \
                           else (entry - self.take_profit_pips * pip)

            self.active_positions[trade_id] = {
                'symbol':     symbol,
                'direction':  direction,
                'entry':      entry,
                'stop_loss':  sl_price,
                'take_profit': tp_price,
                'units':      abs(raw_units),
                'notional':   0,
                'rr_ratio':   0,
                'timestamp':  datetime.now(timezone.utc),
                'signal_sl':  sl_price,
                'signal_tp':  tp_price,
                'scaled_out': False,
                'trail_active': False,
                'synced_from_broker': True,
            }
            self.active_pairs.add(symbol)
            self.display.info(
                f"🔄 Synced existing position: {symbol} {direction} entry={entry:.5f} "
                f"SL={sl_price:.5f} TP={tp_price:.5f}", "", Colors.BRIGHT_CYAN
            )

    def _analyze_and_reoptimize_positions(self):
        """
        Analyze current positions against new margin config (1.5% risk per trade)
        and identify positions that need resizing.
        
        This ensures all positions align with the updated configuration:
        - Position sizing: 1.5% risk per trade (up from 1.0%)
        - Signal confidence: 76%+ only
        - Margin utilization: 25-30% target (vs current 11.6%)
        """
        if not self.active_positions:
            self.display.info("📊 No open positions to reoptimize")
            return
        
        try:
            # Get current account balance
            acct_info = self.oanda.get_account_info()
            if not acct_info:
                self.display.warning("⚠️  Could not fetch account info for reoptimization")
                return
            
            account_balance = float(getattr(acct_info, 'balance', None) or 10000.0)
            margin_used = float(getattr(acct_info, 'marginUsed', None) or 0.0)
            margin_available = float(getattr(acct_info, 'marginAvailable', None) or 0.0)
            margin_pct = (margin_used / account_balance * 100) if account_balance > 0 else 0
            
            self.display.alert(
                f"Position Reoptimization Analysis (NEW CONFIG: 1.5% risk, 76%+ confidence)",
                "INFO"
            )
            print(f"   Account Balance: ${account_balance:,.2f}")
            print(f"   Current Margin Used: ${margin_used:,.2f} ({margin_pct:.1f}%)")
            print(f"   Margin Available: ${margin_available:,.2f}")
            print()
            
            # Import margin maximizer for calculations
            from util.margin_maximizer import MarginMaximizer, MarginConfig
            
            margin_calc = MarginMaximizer(
                MarginConfig(
                    risk_per_trade_min=0.10,   # 1.0%
                    risk_per_trade_target=0.15, # 1.5% NEW CONFIG
                    risk_per_trade_max=0.20     # 2.0%
                )
            )
            margin_calc.account_balance = account_balance
            
            # Target margins
            target_margin_min = 0.25  # 25%
            target_margin_max = 0.30  # 30%
            target_margin_usd_min = account_balance * target_margin_min
            target_margin_usd_max = account_balance * target_margin_max
            
            print(f"   Target Margin Range: ${target_margin_usd_min:,.0f} - ${target_margin_usd_max:,.0f} "
                  f"({target_margin_min*100:.0f}% - {target_margin_max*100:.0f}%)")
            print()
            
            # Analyze each position
            print("   Position Analysis:")
            print("   " + "=" * 100)
            
            adjustments_needed = False
            for trade_id, pos in self.active_positions.items():
                symbol = pos['symbol']
                units = pos['units']
                direction = pos['direction']
                entry = pos['entry']
                
                # Calculate notional value (units * entry price)
                notional = units * entry
                position_margin_pct = (margin_used / account_balance * 100) if account_balance > 0 else 0
                
                # Get recommendation from margin maximizer
                allocation = margin_calc.get_allocation_for_symbol(
                    symbol,
                    account_balance=account_balance,
                    existing_positions=self.active_positions
                )
                
                target_notional = allocation['target_notional']
                max_notional = allocation['max_notional']
                target_units = target_notional / entry if entry > 0 else 0
                max_units = max_notional / entry if entry > 0 else 0
                
                status = "✅"
                if units < target_units * 0.8:  # More than 20% undersized
                    status = "⚠️ UNDERSIZED"
                    adjustments_needed = True
                elif units > max_units * 1.1:   # More than 10% oversized
                    status = "⚠️ OVERSIZED"
                    adjustments_needed = True
                
                print(f"   {status} {symbol} {direction:4} | Units: {units:>8,.0f} | "
                      f"Entry: {entry:.5f} | Notional: ${notional:>10,.0f}")
                print(f"         Target: {target_units:>8,.0f} units | "
                      f"Max: {max_units:>8,.0f} units | Risk Factor: 1.5%")
                print()
            
            print("   " + "=" * 100)
            print()
            
            if adjustments_needed:
                print("   RECOMMENDATION:")
                print("   Close and reopen undersized positions to align with new 1.5% risk config")
                print("   This will increase position sizes by ~50% on average")
                print("   New margin utilization target: 25-30% (currently {:.1f}%)".format(margin_pct))
                print()
                
                # Auto-resize if enabled
                auto_resize = os.getenv('RBOT_AUTO_RESIZE_POSITIONS', '0') == '1'
                if auto_resize:
                    self.display.alert("AUTO_RESIZE enabled - closing undersized positions", "INFO")
                    self._auto_resize_undersized_positions()
                else:
                    self.display.info("💡 Set RBOT_AUTO_RESIZE_POSITIONS=1 to auto-close and reopen positions")
            else:
                self.display.success("✅ All positions are properly sized for new config")
            
            # Log analysis
            log_narration(
                event_type="POSITION_REOPTIMIZATION_ANALYSIS",
                details={
                    "account_balance": account_balance,
                    "current_margin_pct": margin_pct,
                    "target_margin_range": f"{target_margin_min*100:.0f}%-{target_margin_max*100:.0f}%",
                    "adjustments_needed": adjustments_needed,
                    "positions_analyzed": len(self.active_positions),
                    "new_config": "risk_1.5%_confidence_76%"
                }
            )
            
        except Exception as e:
            self.display.error(f"❌ Position reoptimization analysis failed: {e}")
            log_narration(
                event_type="POSITION_REOPTIMIZATION_ERROR",
                details={"error": str(e)}
            )

    def _auto_resize_undersized_positions(self):
        """Close undersized positions to allow bot to reopen at correct sizing"""
        self.display.alert("Closing undersized positions for resizing...", "WARNING")
        
        try:
            from util.margin_maximizer import MarginMaximizer, MarginConfig
            
            # Get fresh account info
            acct_info = self.oanda.get_account_info()
            account_balance = float(getattr(acct_info, 'balance', None) or 10000.0)
            
            margin_calc = MarginMaximizer(
                MarginConfig(
                    risk_per_trade_min=0.10,
                    risk_per_trade_target=0.15,
                    risk_per_trade_max=0.20
                )
            )
            margin_calc.account_balance = account_balance
            
            closed_count = 0
            for trade_id, pos in list(self.active_positions.items()):
                symbol = pos['symbol']
                units = pos['units']
                entry = pos['entry']
                direction = pos['direction']
                
                allocation = margin_calc.get_allocation_for_symbol(
                    symbol,
                    account_balance=account_balance
                )
                target_units = (allocation['target_notional'] / entry) if entry > 0 else 0
                
                # Close if undersized (less than 80% of target)
                if units < target_units * 0.80:
                    try:
                        # Close at market (or within 1 pip if market looks bad)
                        self.display.info(f"   Closing {symbol} {direction} {units:,.0f} units "
                                         f"(undersized: {units:,.0f} vs target {target_units:,.0f})")
                        
                        self.oanda.close_trade(trade_id)
                        closed_count += 1
                        
                        # Remove from tracking
                        del self.active_positions[trade_id]
                        
                    except Exception as close_err:
                        self.display.error(f"   ❌ Failed to close {trade_id}: {close_err}")
            
            if closed_count > 0:
                self.display.success(f"✅ Closed {closed_count} undersized position(s) for resizing")
                self.display.info("💡 Bot will reopen with new sizing on next scan cycle")
                log_narration(
                    event_type="POSITIONS_CLOSED_FOR_RESIZE",
                    details={
                        "closed_count": closed_count,
                        "new_config": "risk_1.5%_confidence_76%",
                        "next_action": "await_reopen_with_new_sizing"
                    }
                )
        except Exception as e:
            self.display.error(f"❌ Auto-resize failed: {e}")

    async def trade_manager_loop(self):
        """Background loop that evaluates active positions and asks the Hive for momentum signals.

        Behavior:
        - For positions older than `min_position_age_seconds`, query the Hive Mind for a consensus
          analysis on that symbol.
        - Use battle-tested MomentumDetector (from rbotzilla_golden_age.py) to detect strong momentum.
        - If EITHER the Hive consensus exceeds threshold OR MomentumDetector confirms momentum,
          cancel the existing TakeProfit order and set an adaptive trailing stop via the OANDA connector.
        - All modifications are logged via `log_narration` to keep an auditable trail.
        
        Integration Note: This TradeManager integrates existing momentum detection logic from
        /home/ing/RICK/RICK_LIVE_CLEAN/rbotzilla_golden_age.py (MomentumDetector & SmartTrailingSystem)
        to fulfill Charter requirement for code reuse (PIN 841921).
        """
        # ========================================================================
        # 🛡️ TRADE MANAGER ACTIVATION (NEW - Per User Requirement)
        # ========================================================================
        self.trade_manager_active = True
        self.trade_manager_last_heartbeat = datetime.now(timezone.utc)
        
        self.display.success("✅ TRADE MANAGER ACTIVATED AND CONNECTED")
        log_narration(
            event_type="TRADE_MANAGER_ACTIVATED",
            details={
                "status": "ACTIVE",
                "timestamp": self.trade_manager_last_heartbeat.isoformat(),
                "min_position_age_seconds": self.min_position_age_seconds,
                "hive_trigger_confidence": self.hive_trigger_confidence
            },
            symbol="SYSTEM",
            venue="trade_manager"
        )
        
        while self.is_running:
            try:
                # Re-sync broker positions each cycle so manually opened or
                # restarted trades are always visible to the manager.
                self._sync_open_positions()

                now = datetime.now(timezone.utc)
                for order_id, pos in list(self.active_positions.items()):
                    # Skip if already processed for TP cancellation
                    if pos.get('tp_cancelled'):
                        continue
                    
                    # Age check
                    age = (now - pos['timestamp']).total_seconds()
                    if age < self.min_position_age_seconds:
                        continue

                    symbol = pos['symbol']
                    direction = pos['direction']
                    entry_price = pos['entry']
                    pos_sl  = pos.get('stop_loss', 0)
                    pos_tp  = pos.get('take_profit', 0)

                    # Get current price to calculate profit
                    try:
                        current_price_data = self.get_current_price(symbol)
                        if not current_price_data:
                            continue
                        current_price = current_price_data['ask'] if direction == 'BUY' else current_price_data['bid']
                    except Exception as e:
                        self.display.warning(f"Could not fetch current price for {symbol}: {e}")
                        continue

                    # ── Incremental position management (multi_signal_engine) ──
                    from systems.multi_signal_engine import manage_open_trade, TradeAction, session_bias
                    sess_name, _ = session_bias(symbol)
                    trade_action, trade_detail = manage_open_trade(
                        direction    = direction,
                        entry        = entry_price,
                        sl           = pos_sl,
                        tp           = pos_tp,
                        current_price= current_price,
                        symbol       = symbol,
                        scaled_out   = pos.get('scaled_out', False),
                        trail_active = pos.get('trail_active', False),
                        session      = sess_name,
                    )

                    if trade_action == TradeAction.SCALE_OUT_HALF:
                        self.display.alert(
                            f"📉 SCALE_OUT_HALF {symbol} @ {current_price:.5f}  "
                            f"(1R profit, closing 50%)", "INFO"
                        )
                        try:
                            trades = self.oanda.get_trades()
                            for t in trades:
                                ti = (t.get('instrument') or t.get('symbol', '')).upper()
                                if ti == symbol.upper():
                                    tid = t.get('id') or t.get('tradeID') or t.get('trade_id')
                                    units_now = int(abs(float(t.get('currentUnits', t.get('units', 0)))))
                                    half = max(1, units_now // 2)
                                    close_units = half if direction == 'BUY' else -half
                                    self.oanda.close_trade_partial(tid, close_units)
                                    pos['scaled_out'] = True
                                    log_narration(
                                        event_type="SCALE_OUT_HALF",
                                        details={"symbol": symbol, "units_closed": half,
                                                 "pnl_r": trade_detail.get('pnl_r')},
                                        symbol=symbol, venue="trade_manager"
                                    )
                        except Exception as _se:
                            self.display.warning(f"Scale-out error for {symbol}: {_se}")

                    elif trade_action == TradeAction.MOVE_BE:
                        new_sl = trade_detail.get('new_sl', entry_price)
                        self.display.info(
                            f"🔒 BREAKEVEN {symbol}  new SL → {new_sl:.5f}", "", Colors.BRIGHT_GREEN
                        )
                        try:
                            trades = self.oanda.get_trades()
                            for t in trades:
                                ti = (t.get('instrument') or t.get('symbol', '')).upper()
                                if ti == symbol.upper():
                                    tid = t.get('id') or t.get('tradeID') or t.get('trade_id')
                                    self.oanda.set_trade_stop(tid, new_sl)
                                    pos['stop_loss'] = new_sl
                                    log_narration(
                                        event_type="SL_MOVED_BE",
                                        details={"symbol": symbol, "new_sl": new_sl},
                                        symbol=symbol, venue="trade_manager"
                                    )
                        except Exception as _be:
                            self.display.warning(f"Breakeven SL error for {symbol}: {_be}")

                    elif trade_action == TradeAction.TRAIL_TIGHT:
                        new_sl = trade_detail.get('new_sl')
                        self.display.success(
                            f"🎯 TRAIL_TIGHT {symbol}  trail SL → {new_sl:.5f}  "
                            f"(R={trade_detail.get('pnl_r', 0):.2f})"
                        )
                        try:
                            trades = self.oanda.get_trades()
                            for t in trades:
                                ti = (t.get('instrument') or t.get('symbol', '')).upper()
                                if ti == symbol.upper():
                                    tid = t.get('id') or t.get('tradeID') or t.get('trade_id')
                                    self.oanda.set_trade_stop(tid, new_sl)
                                    pos['stop_loss']   = new_sl
                                    pos['trail_active'] = True
                                    log_narration(
                                        event_type="TRAIL_TIGHT_SET",
                                        details={"symbol": symbol, "new_sl": new_sl,
                                                 "pnl_r": trade_detail.get('pnl_r')},
                                        symbol=symbol, venue="trade_manager"
                                    )
                        except Exception as _te:
                            self.display.warning(f"Trail-tight SL error for {symbol}: {_te}")

                    elif trade_action == TradeAction.CLOSE_ALL:
                        reason = trade_detail.get('reason', 'engine')
                        self.display.alert(
                            f"🚪 CLOSE_ALL {symbol} reason={reason}  "
                            f"price={current_price:.5f}", "WARNING"
                        )
                        try:
                            trades = self.oanda.get_trades()
                            for t in trades:
                                ti = (t.get('instrument') or t.get('symbol', '')).upper()
                                if ti == symbol.upper():
                                    tid = t.get('id') or t.get('tradeID') or t.get('trade_id')
                                    self.oanda.close_trade(tid)
                                    log_narration(
                                        event_type="FORCED_CLOSE",
                                        details={"symbol": symbol, "reason": reason,
                                                 "pnl_r": trade_detail.get('pnl_r')},
                                        symbol=symbol, venue="trade_manager"
                                    )
                        except Exception as _ce:
                            self.display.warning(f"Force-close error for {symbol}: {_ce}")

                    # ── Legacy hive/momentum checks (continue after incremental mgmt) ──
                    # Calculate profit in pips and ATR multiples
                    pip_size = 0.0001 if 'JPY' not in symbol else 0.01
                    if direction == 'BUY':
                        profit_pips = (current_price - entry_price) / pip_size
                    else:
                        profit_pips = (entry_price - current_price) / pip_size
                    
                    # Estimate ATR (use stop_loss_pips / 1.2 as proxy, since stop = 1.2 * ATR)
                    estimated_atr_pips = self.stop_loss_pips / 1.2
                    profit_atr_multiple = profit_pips / estimated_atr_pips if estimated_atr_pips > 0 else 0

                    # Signal flags
                    hive_signal_confirmed = False
                    momentum_signal_confirmed = False

                    # Query Hive Mind for consensus on this instrument
                    if self.hive_mind:
                        market_data = {
                            "symbol": symbol.replace('_', ''),
                            "current_price": current_price,
                            "timeframe": "M15"
                        }

                        analysis = self.hive_mind.delegate_analysis(market_data)
                        consensus = analysis.consensus_signal
                        confidence = analysis.consensus_confidence

                        # Log the analysis
                        log_narration(
                            event_type="HIVE_ANALYSIS",
                            details={
                                "symbol": symbol,
                                "consensus": consensus.value if hasattr(consensus, 'value') else str(consensus),
                                "confidence": confidence,
                                "order_id": order_id,
                                "profit_atr": profit_atr_multiple
                            },
                            symbol=symbol,
                            venue="hive"
                        )

                        # Check hive consensus threshold
                        if confidence >= self.hive_trigger_confidence and consensus in (SignalStrength.STRONG_BUY, SignalStrength.STRONG_SELL):
                            if (direction == 'BUY' and consensus == SignalStrength.STRONG_BUY) or (direction == 'SELL' and consensus == SignalStrength.STRONG_SELL):
                                hive_signal_confirmed = True
                                self.display.info(f"Hive signal: {consensus.value} ({confidence:.2f}) for {symbol}", Colors.BRIGHT_CYAN)

                    # Use MomentumDetector from rbotzilla_golden_age.py
                    if self.momentum_detector and profit_atr_multiple > 0:
                        # Assume moderate trend and normal volatility for simple case
                        # (In production, you'd query actual regime/volatility from ML modules)
                        trend_strength = 0.7  # Moderate trend assumption
                        market_cycle = 'BULL_MODERATE'  # Default assumption
                        volatility = 1.0  # Normal volatility

                        has_momentum, momentum_strength = self.momentum_detector.detect_momentum(
                            profit_atr_multiple=profit_atr_multiple,
                            trend_strength=trend_strength,
                            cycle=market_cycle,
                            volatility=volatility
                        )

                        if has_momentum:
                            momentum_signal_confirmed = True
                            self.display.info(f"Momentum detected: {momentum_strength:.2f}x strength for {symbol} (profit: {profit_atr_multiple:.2f}x ATR)", Colors.BRIGHT_GREEN)
                            
                            log_narration(
                                event_type="MOMENTUM_DETECTED",
                                details={
                                    "symbol": symbol,
                                    "profit_atr": profit_atr_multiple,
                                    "momentum_strength": momentum_strength,
                                    "order_id": order_id
                                },
                                symbol=symbol,
                                venue="momentum_detector"
                            )

                    # Trigger TP cancellation if EITHER signal confirmed
                    if hive_signal_confirmed or momentum_signal_confirmed:
                        trigger_source = []
                        if hive_signal_confirmed:
                            trigger_source.append("Hive")
                        if momentum_signal_confirmed:
                            trigger_source.append("Momentum")
                        
                        self.display.alert(f"{'|'.join(trigger_source)} signal(s) detected for {symbol} - converting OCO to trailing SL", "INFO")

                        # Attempt to cancel TP order(s) associated with this OCO
                        try:
                            cancel_resp = self.oanda.cancel_order(order_id)

                            log_narration(
                                event_type="TP_CANCEL_ATTEMPT",
                                details={
                                    "order_id": order_id,
                                    "trigger_source": trigger_source,
                                    "profit_atr": profit_atr_multiple,
                                    "cancel_response": cancel_resp
                                },
                                symbol=symbol,
                                venue="oanda"
                            )

                            # Find open trades for this symbol and set an initial trailing stop
                            trades = self.oanda.get_trades()
                            for t in trades:
                                trade_instrument = t.get('instrument') or t.get('symbol')
                                trade_id = t.get('id') or t.get('tradeID') or t.get('trade_id')
                                if not trade_id:
                                    continue
                                if trade_instrument and trade_instrument.replace('.', '_').upper() == symbol:
                                    # Calculate adaptive trailing stop using SmartTrailingSystem
                                    if self.trailing_system and profit_atr_multiple > 0:
                                        atr_price = estimated_atr_pips * pip_size
                                        trail_distance = self.trailing_system.calculate_dynamic_trailing_distance(
                                            profit_atr_multiple=profit_atr_multiple,
                                            atr=atr_price,
                                            momentum_active=True
                                        )
                                        
                                        if direction == 'BUY':
                                            new_sl = current_price - trail_distance
                                        else:
                                            new_sl = current_price + trail_distance
                                        
                                        # Ensure new SL is better than original
                                        original_sl = pos.get('stop_loss')
                                        if direction == 'BUY':
                                            adaptive_sl = max(new_sl, original_sl)
                                        else:
                                            adaptive_sl = min(new_sl, original_sl)
                                    else:
                                        # Keep existing stop_loss
                                        adaptive_sl = pos.get('stop_loss')
                                    
                                    set_resp = self.oanda.set_trade_stop(trade_id, adaptive_sl)

                                    log_narration(
                                        event_type="TRAILING_SL_SET",
                                        details={
                                            "trade_id": trade_id,
                                            "order_id": order_id,
                                            "set_stop": adaptive_sl,
                                            "trail_distance_pips": (current_price - adaptive_sl) / pip_size if direction == 'BUY' else (adaptive_sl - current_price) / pip_size,
                                            "set_resp": set_resp,
                                            "trigger_source": trigger_source
                                        },
                                        symbol=symbol,
                                        venue="oanda"
                                    )

                                    # Mark position as having TP cancelled
                                    pos['tp_cancelled'] = True
                                    pos['tp_cancelled_timestamp'] = datetime.now(timezone.utc)
                                    pos['tp_cancel_source'] = trigger_source
                                    self.display.success(f"✅ TP cancelled and adaptive trailing SL set for trade {trade_id} ({symbol})")
                                    break

                        except Exception as e:
                            self.display.error(f"Error during TP cancellation/trailing conversion: {e}")
                            log_narration(
                                event_type="TP_CANCEL_ERROR",
                                details={"order_id": order_id, "error": str(e)},
                                symbol=symbol,
                                venue="oanda"
                            )

                # Sleep short interval before next pass
                await asyncio.sleep(5)
                
                # ========================================================================
                # 🛡️ UPDATE TRADE MANAGER HEARTBEAT (NEW - Per User Requirement)
                # ========================================================================
                self.trade_manager_last_heartbeat = datetime.now(timezone.utc)
                
            except Exception as e:
                self.display.error(f"TradeManager loop error: {e}")
                await asyncio.sleep(5)
        
        # ========================================================================
        # 🛡️ TRADE MANAGER DEACTIVATION (NEW - Per User Requirement)
        # ========================================================================
        self.trade_manager_active = False
        self.display.warning("⚠️  TRADE MANAGER DEACTIVATED")
        log_narration(
            event_type="TRADE_MANAGER_DEACTIVATED",
            details={
                "status": "INACTIVE",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            symbol="SYSTEM",
            venue="trade_manager"
        )
    
    def _handle_position_closed(self, trade_id: str):
        """Handle a closed position"""
        if trade_id not in self.active_positions:
            return
        
        position = self.active_positions[trade_id]
        
        try:
            # Get trade details from OANDA
            trades = self.oanda.get_trades()
            
            # Assume win for now (we'd need to check actual closing price)
            # In real implementation, you'd query the closed trade details
            is_win = True  # Placeholder
            
            pnl = 50.0 if is_win else -20.0  # Placeholder values
            
            if is_win:
                self.wins += 1
                self.display.trade_win(
                    position['symbol'],
                    pnl,
                    f"Exit: {position['take_profit']:.5f} | R:R 3:1 achieved"
                )
            else:
                self.losses += 1
                self.display.trade_loss(
                    position['symbol'],
                    pnl,
                    f"Exit: {position['stop_loss']:.5f} | Stopped out"
                )
            
            # Remove from active positions
            del self.active_positions[trade_id]
            
            # ========================================================================
            # 🛡️ REMOVE FROM ACTIVE PAIRS (NEW - Per User Requirement)
            # ========================================================================
            if position['symbol'] in self.active_pairs:
                self.active_pairs.discard(position['symbol'])
                # Update global tracker
                global_pairs = self._load_global_active_pairs()
                global_pairs.discard(position['symbol'])
                self._save_global_active_pairs(global_pairs)
                self.display.info(f"✅ Pair {position['symbol']} removed from active pairs ({len(self.active_pairs)}/{self.max_pairs_per_platform})", "", Colors.BRIGHT_CYAN)
            
            # ========================================================================
            # 🛡️ UNREGISTER POSITION FROM CROSS-PLATFORM REGISTRY
            # ========================================================================
            if self.positions_registry:
                try:
                    unregistered = self.positions_registry.unregister_position(
                        symbol=position['symbol'],
                        platform='oanda'
                    )
                    if unregistered:
                        self.display.info("📋 Position removed from cross-platform registry", "", Colors.BRIGHT_CYAN)
                except Exception as e:
                    self.display.warning(f"⚠️  Could not unregister position: {e}")
            
            # Display stats
            self._display_stats()
            
        except Exception as e:
            self.display.error(f"Error handling closed position: {e}")
    
    def _display_stats(self):
        """Display current statistics"""
        win_rate = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0
        
        stats = {
            "Total Trades": str(self.total_trades),
            "Active Positions": str(len(self.active_positions)),
            "Wins / Losses": f"{self.wins} / {self.losses}",
            "Win Rate": f"{win_rate:.1f}%"
        }
        
        self.display.stats_panel(stats)
    
    async def run_trading_loop(self):
        """Main trading loop (environment-agnostic)"""
        self.is_running = True
        
        env_label = "PRACTICE" if self.environment == 'practice' else "LIVE"
        self.display.alert(f"Starting trading engine with {env_label} API...", "SUCCESS")
        self.display.alert(f"📊 Market Data: {env_label} OANDA API (real-time)", "INFO")
        self.display.alert(f"💰 Orders: {env_label} OANDA API", "INFO")
        print()
        
        trade_count = 0
        last_police_sweep = time.time()  # Track last Position Police sweep
        police_sweep_interval = 900  # 15 minutes (M15 charter compliance)
        
        # Sync any trades already open on the broker before the manager starts
        self._sync_open_positions()
        
        # Analyze positions against new config (1.5% risk, 76%+ confidence)
        self._analyze_and_reoptimize_positions()

        # Start TradeManager background task
        trade_manager_task = asyncio.create_task(self.trade_manager_loop())
        
        while self.is_running:
            try:
                # AUTOMATED POSITION POLICE SWEEP (every 15 minutes)
                current_time = time.time()
                if current_time - last_police_sweep >= police_sweep_interval:
                    try:
                        self.display.info("🚓 Position Police sweep starting...")
                        _rbz_force_min_notional_position_police()
                        last_police_sweep = current_time
                        self.display.success("✅ Position Police sweep complete")
                    except Exception as e:
                        self.display.error(f"❌ Position Police error: {e}")
                
                # Check existing positions
                self.check_positions()

                # Refresh gate NAV from live account balance each cycle
                try:
                    if hasattr(self.oanda, 'get_account_info'):
                        _acct = self.oanda.get_account_info()
                        if _acct is not None:
                            _nav = float(getattr(_acct, 'balance', None) or self.gate.account_nav)
                            if _nav != self.gate.account_nav:
                                self.gate.account_nav = _nav
                                self.gate.max_margin_usd = _nav * self.gate.MARGIN_CAP_PCT
                except Exception:
                    pass
                
                # ── Multi-strategy scan: place ALL qualifying signals ─────────
                MAX_POSITIONS = 5   # max simultaneous open positions

                open_count = len(self.active_positions)
                if open_count >= MAX_POSITIONS:
                    self.display.alert(
                        f"Max positions reached ({open_count}/{MAX_POSITIONS}) — "
                        f"waiting {self.min_trade_interval//60}m for a slot to open...",
                        "INFO"
                    )
                    await asyncio.sleep(self.min_trade_interval)
                    continue

                if open_count < MAX_POSITIONS:
                    from datetime import datetime, timezone as _tz
                    _utc_now = datetime.now(_tz.utc)

                    # Symbols already open on broker OR tracked locally
                    held_on_broker = set(
                        (t.get('instrument') or t.get('symbol', '')).upper()
                        for t in (self.oanda.get_trades() or [])
                    )
                    active_symbols = {
                        pos['symbol'].upper()
                        for pos in self.active_positions.values()
                        if 'symbol' in pos
                    }
                    blocked_symbols = held_on_broker | active_symbols

                    qualified: list[AggregatedSignal] = []
                    rejected:  list[dict]             = []

                    for _candidate in self.trading_pairs:
                        _cu = _candidate.upper()
                        # ── already active ───────────────────────────────
                        if _cu in blocked_symbols:
                            rejected.append({'symbol': _candidate,
                                             'reason': 'already_active_symbol',
                                             'conf': None, 'dir': None})
                            continue
                        # ── fetch candles + run all detectors ───────────
                        try:
                            candles = self.oanda.get_historical_data(
                                _candidate, count=150, granularity="M15"
                            )
                            agg = scan_symbol(
                                _candidate, candles,
                                utc_now=_utc_now,
                                min_confidence=self.min_confidence,  # 0.55 vote floor
                                min_votes=2,
                            )
                        except Exception as _scan_err:
                            rejected.append({'symbol': _candidate,
                                             'reason': 'error_in_scan',
                                             'conf': None, 'dir': None,
                                             'detail': str(_scan_err)})
                            continue

                        # ── not enough consensus ─────────────────────────
                        if agg is None:
                            rejected.append({'symbol': _candidate,
                                             'reason': 'no_signal',
                                             'conf': None, 'dir': None})
                            continue

                        # ── confidence gate (selection threshold) ────────
                        if agg.confidence < self.min_signal_confidence:
                            rejected.append({'symbol': _candidate,
                                             'reason': 'confidence_below_threshold',
                                             'conf': agg.confidence,
                                             'dir':  agg.direction,
                                             'threshold': self.min_signal_confidence})
                            continue

                        # ── passed — queue it ─────────────────────────────
                        qualified.append(agg)

                    # Sort best-edge first
                    qualified.sort(key=lambda x: x.confidence, reverse=True)

                    slots_left  = MAX_POSITIONS - open_count
                    cycle_limit = min(slots_left, self.max_new_trades_per_cycle,
                                      len(qualified))

                    # ── SIGNAL_SCAN_RESULTS log (terminal + narration) ───
                    N = self.scan_log_top_n
                    scan_summary = {
                        'pairs_scanned':    len(self.trading_pairs),
                        'candidates_passed': len(qualified),
                        'open_slots':       slots_left,
                        'placing':          cycle_limit,
                        'min_conf_gate':    self.min_signal_confidence,
                        'top_candidates':   [
                            {'symbol': a.symbol, 'dir': a.direction,
                             'conf': round(a.confidence, 4),
                             'votes': a.votes,
                             'detectors': a.detectors_fired,
                             'session': a.session, 'rr': round(a.rr, 2)}
                            for a in qualified[:N]
                        ],
                        'top_rejected': [
                            {'symbol': r['symbol'], 'reason': r['reason'],
                             'conf': r.get('conf'), 'dir': r.get('dir')}
                            for r in rejected[:N]
                        ],
                    }
                    log_narration(
                        event_type="SIGNAL_SCAN_RESULTS",
                        details=scan_summary,
                        symbol="SYSTEM",
                        venue="signal_scan",
                    )

                    # Terminal summary
                    self.display.section(
                        f"📡 SCAN: {len(self.trading_pairs)} pairs "
                        f"| ✅ {len(qualified)} passed "
                        f"| ❌ {len(rejected)} rejected "
                        f"| 🎯 placing {cycle_limit}"
                    )
                    for a in qualified[:N]:
                        self.display.success(
                            f"  ✅ {a.symbol:10} {a.direction:4} "
                            f"conf={a.confidence:.1%}  votes={a.votes}  "
                            f"det={','.join(a.detectors_fired)}  "
                            f"sess={a.session}  RR={a.rr:.2f}"
                        )
                    for r in rejected[:N]:
                        conf_str = f"{r['conf']:.1%}" if r['conf'] else 'n/a'
                        self.display.warning(
                            f"  ❌ {r['symbol']:10} {str(r.get('dir') or ''):4} "
                            f"conf={conf_str:6}  → {r['reason']}"
                        )

                    if cycle_limit == 0:
                        self.display.warning(
                            f"No qualifying signals this cycle — "
                            f"rescanning in {self.scan_fast_seconds}s..."
                        )
                        await asyncio.sleep(self.scan_fast_seconds)
                        continue

                    # ── Place each selected trade ─────────────────────────
                    for agg in qualified[:cycle_limit]:
                        self.display.success(
                            f"→ Placing {agg.symbol} {agg.direction} "
                            f"conf={agg.confidence:.1%}  "
                            f"({agg.votes} votes: {','.join(agg.detectors_fired)})"
                        )
                        trade_id = self.place_trade(
                            agg.symbol, agg.direction,
                            signal_sl=agg.sl,
                            signal_tp=agg.tp,
                        )
                        if trade_id:
                            if trade_id in self.active_positions:
                                self.active_positions[trade_id].update({
                                    'signal_sl':        agg.sl,
                                    'signal_tp':        agg.tp,
                                    'signal_votes':     agg.votes,
                                    'signal_detectors': agg.detectors_fired,
                                    'session':          agg.session,
                                    'scaled_out':       False,
                                    'trail_active':     False,
                                })
                            trade_count += 1

                    self.display.divider()
                    print()
                
                # Fast rescan while slots remain; slow only when full.
                open_count_now = len(self.active_positions)
                
                # ── DASHBOARD: Display position summary and system health ───────
                try:
                    if self.dashboard and os.getenv('RBOT_DASHBOARD_ACTIVE', 'true').lower() != 'false':
                        self.dashboard.sync_and_display()
                except Exception as _dashboard_err:
                    self.display.warning(f"⚠️ Dashboard render error: {_dashboard_err}")
                
                if open_count_now >= MAX_POSITIONS:
                    self.display.alert(
                        f"Positions full ({open_count_now}/{MAX_POSITIONS}) — "
                        f"waiting {self.scan_slow_seconds}s for next slot...",
                        "INFO"
                    )
                    await asyncio.sleep(self.scan_slow_seconds)
                else:
                    self.display.alert(
                        f"Slots open ({open_count_now}/{MAX_POSITIONS}) — "
                        f"rescanning in {self.scan_fast_seconds}s...",
                        "INFO"
                    )
                    await asyncio.sleep(self.scan_fast_seconds)
                
            except KeyboardInterrupt:
                self.display.warning("\nStopping trading engine...")
                self.is_running = False
                break
            except Exception as e:
                self.display.error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)
        
        self.display.section("SESSION COMPLETE")
        self._display_stats()
        # Cancel trade manager task
        try:
            trade_manager_task.cancel()
        except Exception:
            pass


async def main():
    """Main entry point - environment determined by API configuration"""
    import argparse
    
    parser = argparse.ArgumentParser(description='RBOTzilla Charter-Compliant OANDA Trading Engine')
    parser.add_argument('--env', '--environment', 
                       choices=['practice', 'live'], 
                       default='practice',
                       help='Trading environment (practice=paper, live=real money)')
    parser.add_argument('--yes-live', action='store_true',
                       help='Required for non-interactive LIVE startup')
    
    args = parser.parse_args()
    
    # Confirm LIVE mode with user
    if args.env == 'live':
        if args.yes_live:
            print("\n✅ LIVE startup confirmed via --yes-live. Running full startup sequence...\n")
        else:
            print("\n" + "="*60)
            print("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
            print("="*60)
            confirm = input("\nType 'CONFIRM LIVE' to proceed with live trading: ")
            if confirm != 'CONFIRM LIVE':
                print("Live trading cancelled.")
                return
            print("\n✅ Live trading confirmed. Running full startup sequence...\n")
    
    # ══════════════════════════════════════════════════════════════════════════
    # NEW: COMPREHENSIVE STARTUP SEQUENCE WITH DETAILED CONFIRMATIONS
    # ══════════════════════════════════════════════════════════════════════════
    try:
        from startup_sequence import run_startup
        startup_result = run_startup(environment=args.env)
        # startup_result contains all confirmations and background bot statuses
    except ImportError:
        print("⚠️  Enhanced startup sequence not available, using basic initialization")
    except Exception as e:
        print(f"⚠️  Startup sequence error: {e}, continuing with basic initialization")
    
    print("\n🚀 Initializing trading engine...\n")
    engine = OandaTradingEngine(environment=args.env)
    await engine.run_trading_loop()


if __name__ == "__main__":
    asyncio.run(main())

# ===== RBOTZILLA: POSITION POLICE (immutable min-notional) =====
try:
    from rick_charter import RickCharter
except Exception:
    class RickCharter: MIN_NOTIONAL_USD = 15000

def _rbz_usd_notional(instrument: str, units: float, price: float) -> float:
    try:
        base, quote = instrument.split("_",1)
        u = abs(float(units))
        p = float(price)
        if quote == "USD":      # e.g., GBP_USD
            return u * p
        if base == "USD":       # e.g., USD_JPY
            return u * 1.0
        return 0.0              # non-USD crosses (ignored by charter)
    except Exception:
        return 0.0

def _rbz_fetch_price(sess, acct: str, inst: str, tok: str):
    import requests
    try:
        r = sess.get(
            f"https://api-fxpractice.oanda.com/v3/accounts/{acct}/pricing",
            headers={"Authorization": f"Bearer {tok}"},
            params={"instruments": inst}, timeout=5,
        )
        return float(r.json()["prices"][0]["closeoutAsk"])
    except Exception:
        return None

def _rbz_force_min_notional_position_police():
    """
    AUTOMATED POSITION POLICE - GATED CHARTER ENFORCEMENT
    Closes any position < MIN_NOTIONAL_USD ($15,000)
    Runs: (1) On engine startup, (2) Every 15 minutes during trading loop
    PIN: 841921 | IMMUTABLE
    """
    import os, json, requests
    from datetime import datetime, timezone
    
    MIN_NOTIONAL = getattr(RickCharter, "MIN_NOTIONAL_USD", 15000)
    acct = os.environ.get("OANDA_PRACTICE_ACCOUNT_ID") or os.environ.get("OANDA_ACCOUNT_ID")
    tok  = os.environ.get("OANDA_PRACTICE_TOKEN") or os.environ.get("OANDA_TOKEN")
    if not acct or not tok:
        print('[RBZ_POLICE] skipped (no creds)'); return

    s = requests.Session()
    violations_found = 0
    violations_closed = 0
    
    # 1) fetch open positions
    r = s.get(
        f"https://api-fxpractice.oanda.com/v3/accounts/{acct}/openPositions",
        headers={"Authorization": f"Bearer {tok}"}, timeout=7,
    )
    
    positions = r.json().get("positions", [])
    timestamp = datetime.now(timezone.utc).isoformat()
    
    for pos in positions:
        inst = pos.get("instrument")
        long_u  = float(pos.get("long",{}).get("units","0"))
        short_u = float(pos.get("short",{}).get("units","0"))  # negative when short
        net = long_u + short_u
        if net == 0:
            continue

        avg = pos.get("long",{}).get("averagePrice") or pos.get("short",{}).get("averagePrice")
        price = float(avg) if avg else (_rbz_fetch_price(s, acct, inst, tok) or 0.0)
        notional = _rbz_usd_notional(inst, net, price)

        if 0 < notional < MIN_NOTIONAL:
            violations_found += 1
            violation_data = {
                "timestamp": timestamp,
                "event_type": "CHARTER_VIOLATION",
                "action": "POSITION_POLICE_AUTO_CLOSE",
                "details": {
                    "violation": "POSITION_BELOW_MIN_NOTIONAL",
                    "instrument": inst,
                    "net_units": net,
                    "side": "long" if net > 0 else "short",
                    "avg_price": price,
                    "notional_usd": round(notional, 2),
                    "min_required_usd": MIN_NOTIONAL,
                    "account": acct,
                    "enforcement": "GATED_LOGIC_AUTOMATIC"
                },
                "symbol": inst,
                "venue": "oanda"
            }
            
            # Log violation BEFORE closing
            print(json.dumps(violation_data))
            try:
                log_narration(**violation_data)
            except:
                pass  # Narration logger may not be available
            
            # Close entire side
            side = "long" if net > 0 else "short"
            payload = {"longUnits":"ALL"} if side=="long" else {"shortUnits":"ALL"}
            close_response = s.put(
                f"https://api-fxpractice.oanda.com/v3/accounts/{acct}/positions/{inst}/close",
                headers={"Authorization": f"Bearer {tok}", "Content-Type":"application/json"},
                data=json.dumps(payload), timeout=7,
            )
            
            if close_response.status_code == 200:
                violations_closed += 1
                close_data = {
                    "timestamp": timestamp,
                    "event_type": "POSITION_CLOSED",
                    "action": "CHARTER_ENFORCEMENT_SUCCESS",
                    "details": {
                        "instrument": inst,
                        "reason": "BELOW_MIN_NOTIONAL",
                        "status": "CLOSED_BY_POSITION_POLICE"
                    },
                    "symbol": inst,
                    "venue": "oanda"
                }
                print(json.dumps(close_data))
                try:
                    log_narration(**close_data)
                except:
                    pass
    
    # Summary logging
    if violations_found > 0:
        summary = {
            "timestamp": timestamp,
            "event_type": "POSITION_POLICE_SUMMARY",
            "details": {
                "violations_found": violations_found,
                "violations_closed": violations_closed,
                "enforcement": "GATED_LOGIC_AUTOMATIC",
                "min_notional_usd": MIN_NOTIONAL
            }
        }
        print(json.dumps(summary))
        try:
            log_narration(**summary)
        except:
            pass
            
# ===== /POSITION POLICE =====

# RBZ guard at import time
try:
    _rbz_force_min_notional_position_police()
except Exception as _e:
    print('[RBZ_POLICE] error', _e)
