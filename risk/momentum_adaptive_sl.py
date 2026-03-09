#!/usr/bin/env python3
"""
MOMENTUM-BASED ADAPTIVE STOP LOSS SYSTEM
=========================================

Analyzes winning vs losing trades and implements intelligent SL management:
1. Calculate momentum for each trade at entry
2. Set dynamic SL based on momentum strength (not fixed pips)
3. Quick exit if trade goes negative unexpectedly
4. Adaptive trailing for momentum trades
5. Reallocate capital from losers to winners

PIN: 841921 | Charter Compliant
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone
import math
import json
from pathlib import Path


@dataclass
class TradeMetrics:
    """Comprehensive metrics for analyzing trade quality"""
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    
    # Momentum at entry
    momentum_strength: float  # 0-1, how strong was the momentum signal
    momentum_type: str        # STRONG_ACCELERATION, MODERATE, WEAK, REVERSAL
    entry_volatility: float   # ATR at entry
    
    # Risk/Reward
    units: int
    stop_loss: float
    take_profit: float
    sl_distance_pips: float
    tp_distance_pips: float
    rr_ratio: float
    
    # Performance
    pnl_usd: float
    pnl_pct: float
    pnl_r: float  # How many R multiples was the profit
    max_profit: float  # Best price reached during trade
    max_loss: float   # Worst price reached during trade
    max_drawdown_pct: float
    
    # Duration and speed
    duration_seconds: int
    bars_to_tp: int  # How many 15-min bars until TP
    bars_to_sl: int  # How many bars until SL
    
    # Outcome
    outcome: str  # WIN_FULL_TP, WIN_PARTIAL, LOSS_SL, CLOSE_EARLY, CLOSE_LATE
    
    # Quality metrics
    trade_quality_score: float = 0.0  # Computed
    momentum_efficiency: float = 0.0   # How well momentum was captured
    

@dataclass  
class MomentumProfile:
    """Momentum characteristics of a market at trade entry"""
    symbol: str
    timestamp: datetime
    
    # Core momentum metrics
    price_acceleration: float  # Rate of price change
    volume_acceleration: float  # Volume increase
    rsi: float  # 0-100
    macd_histogram: float  # Positive = up momentum
    momentum_change: float  # Rate of momentum change
    
    # Derived
    momentum_strength: float  # 0-1 scale
    momentum_type: str  # Type classification
    expected_move_pips: float  # How far we expect price to move
    confidence: float  # How confident in the momentum
    
    # Risk at this momentum level
    recommended_sl_pips: float  # SL distance based on momentum
    recommended_tp_distance: float  # TP distance for 3.2:1 RR
    

@dataclass
class AdaptiveStopLoss:
    """Real-time stop loss that adjusts based on momentum and P&L"""
    trade_id: str
    symbol: str
    entry_price: float
    direction: str
    pip_size: float
    
    # Initial SL (momentum-based)
    initial_sl: float
    initial_sl_pips: float
    momentum_profile: MomentumProfile = None
    
    # Current SL state
    current_sl: float = None
    sl_mode: str = "ORIGINAL"  # ORIGINAL, BREAKEVEN, MOMENTUM_TRAIL, RED_ALERT, CLOSED
    
    # Tracking
    sl_movements: List[Dict] = field(default_factory=list)
    red_alert_triggered: bool = False
    red_alert_threshold: float = -0.5  # -50pips
    
    def __post_init__(self):
        self.current_sl = self.initial_sl
    
    def evaluate(self, current_price: float, momentum_current: MomentumProfile = None) -> Dict:
        """
        Evaluate SL and return recommendation based on:
        1. Current P&L
        2. Expected move from momentum
        3. Time in trade
        4. Volatility changes
        
        Return: {'action': 'HOLD|MOVE_SL|CLOSE_NOW', 'new_sl': ..., 'reason': ...}
        """
        pip_size = self.pip_size
        
        if self.direction == "BUY":
            pnl_pips = (current_price - self.entry_price) / pip_size
            distance_to_current_sl = (current_price - self.current_sl) / pip_size
        else:
            pnl_pips = (self.entry_price - current_price) / pip_size
            distance_to_current_sl = (self.current_sl - current_price) / pip_size
        
        # ════════════════════════════════════════════════════════════════
        # RED ALERT: Trade going negative unexpectedly
        # ════════════════════════════════════════════════════════════════
        if pnl_pips < -0.5 and not self.red_alert_triggered:
            # Expected positive move but went red
            if self.momentum_profile and self.momentum_profile.momentum_strength >= 0.65:
                self.red_alert_triggered = True
                return {
                    'action': 'RED_ALERT',
                    'severity': 'CRITICAL',
                    'reason': f'Trade RED {pnl_pips:.1f}pips despite {self.momentum_profile.momentum_strength:.0%} momentum',
                    'current_pnl': pnl_pips,
                    'expected_move': self.momentum_profile.expected_move_pips,
                    'recommendation': 'CLOSE_FAST'
                }
        
        # ════════════════════════════════════════════════════════════════
        # MOMENTUM BREAKEVEN: Move to breakeven after meaningful profit
        # FIX #2: Threshold raised 0.5 → 8 pips so rbz_tight_trailing.py
        # remains the SOLE authority for early SL movement.  This system
        # only activates later when the trade has genuinely committed.
        # ════════════════════════════════════════════════════════════════
        if 8.0 < pnl_pips <= 15.0 and self.sl_mode == "ORIGINAL":
            # Lock in meaningful profit (above M15 noise level)
            new_sl = self.entry_price
            self.current_sl = new_sl
            self.sl_mode = "BREAKEVEN"
            
            self.sl_movements.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'trigger': 'MOMENTUM_BREAKEVEN_LOCK',
                'old_sl': new_sl,
                'new_sl': new_sl,
                'pnl_at_move': pnl_pips
            })
            
            return {
                'action': 'MOVE_SL',
                'new_sl': new_sl,
                'reason': f'Momentum breakeven: {pnl_pips:.1f}pips → moved to BE (above M15 noise)',
                'pnl_pips': pnl_pips
            }
        
        # ════════════════════════════════════════════════════════════════
        # MOMENTUM TRAIL: Tight trail as momentum carries trade
        # ════════════════════════════════════════════════════════════════
        if pnl_pips >= 1.0 and momentum_current:
            if momentum_current.momentum_strength >= 0.70:
                # Strong momentum - use tight trail to protect gains
                trail_distance = momentum_current.entry_volatility * 1.2  # 1.2x ATR
                
                if self.direction == "BUY":
                    new_sl = current_price - (trail_distance / pip_size)
                    if new_sl > self.current_sl:  # Only trail upward
                        self.current_sl = new_sl
                        self.sl_mode = "MOMENTUM_TRAIL"
                        
                        return {
                            'action': 'MOVE_SL',
                            'new_sl': new_sl,
                            'reason': f'Momentum trail ({momentum_current.momentum_strength:.0%}): {distance_to_current_sl:.1f} pips buffer',
                            'pnl_pips': pnl_pips,
                            'momentum_strength': momentum_current.momentum_strength
                        }
                else:
                    new_sl = current_price + (trail_distance / pip_size)
                    if new_sl < self.current_sl:
                        self.current_sl = new_sl
                        self.sl_mode = "MOMENTUM_TRAIL"
                        
                        return {
                            'action': 'MOVE_SL',
                            'new_sl': new_sl,
                            'reason': f'Momentum trail ({momentum_current.momentum_strength:.0%}): {distance_to_current_sl:.1f} pips buffer',
                            'pnl_pips': pnl_pips,
                            'momentum_strength': momentum_current.momentum_strength
                        }
        
        # ════════════════════════════════════════════════════════════════
        # Normal hold
        # ════════════════════════════════════════════════════════════════
        return {
            'action': 'HOLD',
            'current_sl': self.current_sl,
            'pnl_pips': pnl_pips,
            'distance_to_sl': distance_to_current_sl,
            'reason': f'SL at {self.current_sl:.5f} ({self.sl_mode} mode)'
        }


class WinningTradeAnalyzer:
    """Analyze what made trades win - extract patterns from profitable trades"""
    
    def __init__(self):
        self.winning_trades: List[TradeMetrics] = []
        self.losing_trades: List[TradeMetrics] = []
        self.patterns: Dict[str, float] = {}
    
    def add_trade(self, trade: TradeMetrics):
        """Classify and store trade for analysis"""
        if trade.pnl_usd > 0:
            self.winning_trades.append(trade)
        else:
            self.losing_trades.append(trade)
    
    def analyze_winning_pattern(self) -> Dict:
        """Extract common patterns from winning trades"""
        if not self.winning_trades:
            return {}
        
        # What momentum strength do winners have?
        avg_momentum = sum(t.momentum_strength for t in self.winning_trades) / len(self.winning_trades)
        
        # What SL distances work best?
        avg_sl_pips = sum(t.sl_distance_pips for t in self.winning_trades) / len(self.winning_trades)
        
        # How fast do they win?
        avg_time_to_profit = sum(t.duration_seconds for t in self.winning_trades if t.pnl_usd > 0) / \
                            len([t for t in self.winning_trades if t.duration_seconds])
        
        # What RR ratio do winners have?
        avg_rr = sum(t.rr_ratio for t in self.winning_trades) / len(self.winning_trades)
        
        # Momentum type breakdown
        momentum_types = {}
        for t in self.winning_trades:
            momentum_types[t.momentum_type] = momentum_types.get(t.momentum_type, 0) + 1
        
        # Win rate by momentum type
        win_rate_by_momentum = {}
        for m_type in momentum_types:
            wins_by_type = len([t for t in self.winning_trades if t.momentum_type == m_type])
            all_by_type = wins_by_type + len([t for t in self.losing_trades if t.momentum_type == m_type])
            if all_by_type > 0:
                win_rate_by_momentum[m_type] = wins_by_type / all_by_type
        
        return {
            'count': len(self.winning_trades),
            'avg_momentum_strength': avg_momentum,
            'avg_sl_distance_pips': avg_sl_pips,
            'avg_time_to_profit_seconds': avg_time_to_profit,
            'avg_rr_ratio': avg_rr,
            'momentum_type_distribution': momentum_types,
            'win_rate_by_momentum_type': win_rate_by_momentum,
            'best_momentum_type': max(win_rate_by_momentum, key=win_rate_by_momentum.get) if win_rate_by_momentum else None,
            'best_momentum_win_rate': max(win_rate_by_momentum.values()) if win_rate_by_momentum else 0
        }
    
    def compare_winners_vs_losers(self) -> Dict:
        """Compare winning and losing trades to find edge"""
        if not self.winning_trades or not self.losing_trades:
            return {}
        
        winners_avg_momentum = sum(t.momentum_strength for t in self.winning_trades) / len(self.winning_trades)
        losers_avg_momentum = sum(t.momentum_strength for t in self.losing_trades) / len(self.losing_trades)
        
        winners_avg_rr = sum(t.rr_ratio for t in self.winning_trades) / len(self.winning_trades)
        losers_avg_rr = sum(t.rr_ratio for t in self.losing_trades) / len(self.losing_trades)
        
        winners_avg_time = sum(t.duration_seconds for t in self.winning_trades) / len(self.winning_trades)
        losers_avg_time = sum(t.duration_seconds for t in self.losing_trades) / len(self.losing_trades)
        
        return {
            'momentum_advantage': winners_avg_momentum - losers_avg_momentum,
            'winners_avg_momentum': winners_avg_momentum,
            'losers_avg_momentum': losers_avg_momentum,
            'rr_advantage': winners_avg_rr - losers_avg_rr,
            'winners_avg_rr': winners_avg_rr,
            'losers_avg_rr': losers_avg_rr,
            'time_advantage_seconds': winners_avg_time - losers_avg_time,
            'winners_avg_time': winners_avg_time,
            'losers_avg_time': losers_avg_time,
            'insight': f'Winners have {(winners_avg_momentum/losers_avg_momentum - 1)*100:.1f}% stronger momentum'
        }


class ReallocateCapital:
    """Intelligently reallocate capital from losers to winners"""
    
    def __init__(self, total_account_nav: float):
        self.total_nav = total_account_nav
        self.position_allocation: Dict[str, float] = {}  # symbol -> USD allocation
        self.winning_positions: Dict[str, float] = {}
        self.losing_positions: Dict[str, float] = {}
    
    def evaluate_reallocation(self, open_positions: Dict[str, Dict]) -> Dict[str, float]:
        """
        Analyze open positions and recommend reallocation:
        - Winners: Keep capital, maybe add more
        - Losers: Reduce size or close if not improving
        
        Return: {'symbol': new_allocation_pct}
        """
        reallocation = {}
        
        for symbol, pos in open_positions.items():
            pnl = pos.get('pnl_usd', 0)
            pnl_pct = pos.get('pnl_pct', 0)
            notional = pos.get('notional_usd', 10000)
            
            if pnl > 0:
                # Winning position - can add more (up to max)
                self.winning_positions[symbol] = notional
                
                # If winning strong, add 10% more capital
                if pnl_pct > 1.0:
                    new_notional = notional * 1.10
                    max_per_symbol = self.total_nav * 0.25  # Max 25% per symbol
                    reallocation[symbol] = min(new_notional, max_per_symbol)
                else:
                    reallocation[symbol] = notional
            
            else:
                # Losing position - reduce or close
                self.losing_positions[symbol] = notional
                
                # If losing >2%, close it
                if pnl_pct < -2.0:
                    reallocation[symbol] = 0  # Close
                # If losing 1-2%, reduce by half
                elif pnl_pct < -1.0:
                    reallocation[symbol] = notional * 0.5
                else:
                    reallocation[symbol] = notional
        
        return reallocation


def calculate_momentum_profile(symbol: str, recent_candles: List[Dict]) -> MomentumProfile:
    """
    Calculate detailed momentum profile from candle data
    
    Inputs:
    - recent_candles: List of OHLCV dicts with last 20 candles (M15)
    
    Returns:
    - MomentumProfile with all metrics
    """
    if not recent_candles or len(recent_candles) < 5:
        return None
    
    # Extract price series
    closes = [c['close'] for c in recent_candles]
    volumes = [c['volume'] for c in recent_candles]
    highs = [c['high'] for c in recent_candles]
    lows = [c['low'] for c in recent_candles]
    
    # Price acceleration: rate of change of price change
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    price_accel = changes[-1] - changes[-2] if len(changes) >= 2 else 0
    
    # Volume acceleration
    vol_changes = [volumes[i] - volumes[i-1] for i in range(1, len(volumes))]
    vol_accel = vol_changes[-1] - vol_changes[-2] if len(vol_changes) >= 2 else 0
    
    # RSI (14 period approximation with fewer candles)
    deltas = [changes[i] for i in range(len(changes))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    rsi = 100 - (100 / (1 + rs)) if rs >= 0 else 0

    # FIX #5: MACD using proper EMA weighting (was incorrectly using SMA)
    def _ema_calc(prices: list, period: int) -> float:
        """Proper exponential moving average."""
        if not prices:
            return 0.0
        k = 2.0 / (period + 1)
        val = prices[0]
        for p in prices[1:]:
            val = p * k + val * (1 - k)
        return val

    ema_12 = _ema_calc(closes, 12)
    ema_26 = _ema_calc(closes, 26)
    macd = ema_12 - ema_26
    macd_histogram = macd

    # FIX #5: Stabilize momentum_change to prevent division-by-near-zero spikes
    last_bar_move = closes[-1] - closes[-2]
    # Guard: if last bar barely moved, don't divide into it
    if abs(last_bar_move) > 1e-6:
        momentum_change = price_accel / abs(last_bar_move)
    else:
        momentum_change = 0.0
    # Hard cap to prevent instability-driven false STRONG_ACCELERATION signals
    momentum_change = max(-5.0, min(5.0, momentum_change))

    # Classify momentum type
    if abs(price_accel) > 0.0002 and vol_accel > 0:
        momentum_type = "STRONG_ACCELERATION"
        # FIX #5: was min(1.0, ...) which allowed misleading 1.0 values
        # Now capped at 0.95 and uses a more stable formula
        momentum_strength = min(0.95, 0.65 + abs(momentum_change) * 0.06)
    elif abs(price_accel) > 0.0001:
        momentum_type = "MODERATE"
        momentum_strength = 0.65
    elif abs(momentum_change) > 0.5:
        momentum_type = "REVERSAL"
        momentum_strength = 0.40
    else:
        momentum_type = "WEAK"
        momentum_strength = 0.30
    
    # Expected move based on ATR
    atr = sum([highs[i] - lows[i] for i in range(len(highs))]) / len(highs)
    expected_move_pips = atr / (0.0001 if "JPY" not in symbol else 0.01) * momentum_strength
    
    # Confidence: how sure are we about this momentum
    confidence = min(0.95, momentum_strength + (abs(rsi - 50) / 100))
    
    # SL distance based on momentum: stronger momentum = shorter SL
    # Weak momentum = wider SL to avoid shakeouts
    if momentum_strength >= 0.75:
        recommended_sl_pips = 5  # Tight SL for strong momentum
    elif momentum_strength >= 0.60:
        recommended_sl_pips = 8  # Normal SL
    else:
        recommended_sl_pips = 12  # Wider SL for weak momentum
    
    # TP distance for 3.2:1 RR
    recommended_tp_distance = recommended_sl_pips * 3.2
    
    return MomentumProfile(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        price_acceleration=price_accel,
        volume_acceleration=vol_accel,
        rsi=rsi,
        macd_histogram=macd_histogram,
        momentum_change=momentum_change,
        momentum_strength=momentum_strength,
        momentum_type=momentum_type,
        expected_move_pips=expected_move_pips,
        confidence=confidence,
        recommended_sl_pips=recommended_sl_pips,
        recommended_tp_distance=recommended_tp_distance
    )


# ════════════════════════════════════════════════════════════════════════════
# PRACTICAL EXAMPLE: Your EUR_USD and NZD_USD Winning Trades
# ════════════════════════════════════════════════════════════════════════════

"""
FROM YOUR DATA:
✅ NZD_USD CLOSED: Entry 0.59576, Exit 0.59525 → +$49.95 (WIN)
   - 25,100 units
   - Duration: SHORT (fast exit = good trend ID)
   
✅ EUR_USD FILLED: Entry 1.17060, 82.05 profit on partial (WIN path)
   - 12,800 units → Strong momentum maintained

What made these WIN:
1. STRONG MOMENTUM AT ENTRY: Fast detection + execution
2. QUICK TP HIT: Momentum continued → TP filled before volatility reversed
3. TIGHT SL: Let trade breathe slightly but closed fast if wrong
4. SIZE APPROPRIATE: $15k+ notional = proper position sizing
5. MULTIPLE ENTRY: Different detectors confirmed same signal

Implementation: When you enter based on STRONG momentum (77%+ confidence):
- Set SL at 6 pips (momentum-based, not fixed 10)
- If price goes against you in first 2 candles: CLOSE FAST
- If price confirms momentum: SCALE IN (add 25% more)
- Trail SL tight as momentum continues (0.5-1.0x ATR)
"""
