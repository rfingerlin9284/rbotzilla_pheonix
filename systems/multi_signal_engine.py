"""
Multi-Signal Engine — RBOTzilla Phoenix
Runs every candle-based detector in parallel, votes, and returns the
highest-confidence aggregated signal across ALL strategies for a symbol.

Detectors (all run from raw OANDA candles, zero external deps):
  1. MomentumSMA   — SMA20/50 crossover + rate-of-change
  2. EMAStack      — EMA8/21/55 stacked trend + crossover
  3. FVG           — Fair Value Gap (3-candle imbalance zone)
  4. Fibonacci     — Swing-high/low retracements (0.236–0.786)
  5. LiqSweep      — Liquidity sweep of equal highs/lows + reversal
  6. TrapReversal  — Pin-bar / engulfing trap at key levels
  7. SessionBias   — Caps confidence outside high-probability sessions

Incremental trade-management signals:
  - "SCALE_OUT_HALF"   when price crosses 1R profit
  - "TRAIL_TIGHT"      when price crosses 2R profit
  - "CLOSE_ALL"        when price reverts past trailing level or session ends

PIN: 841921
"""

from __future__ import annotations
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _closes(candles: list) -> list[float]:
    out = []
    for c in candles:
        if isinstance(c, dict):
            v = c.get("mid", {}).get("c") or c.get("close") or c.get("c")
            if v:
                out.append(float(v))
    return out


def _highs(candles: list) -> list[float]:
    out = []
    for c in candles:
        if isinstance(c, dict):
            v = c.get("mid", {}).get("h") or c.get("high") or c.get("h")
            if v:
                out.append(float(v))
    return out


def _lows(candles: list) -> list[float]:
    out = []
    for c in candles:
        if isinstance(c, dict):
            v = c.get("mid", {}).get("l") or c.get("low") or c.get("l")
            if v:
                out.append(float(v))
    return out


def _sma(seq: list[float], n: int) -> float:
    if len(seq) < n:
        return sum(seq) / max(len(seq), 1)
    return sum(seq[-n:]) / n


def _ema(seq: list[float], n: int) -> float:
    if not seq:
        return 0.0
    k = 2.0 / (n + 1)
    val = seq[0]
    for p in seq[1:]:
        val = p * k + val * (1 - k)
    return val


def _roc(seq: list[float], n: int = 10) -> float:
    if len(seq) <= n:
        return 0.0
    a, b = float(seq[-n - 1]), float(seq[-1])
    return (b - a) / max(abs(a), 1e-9) * 100.0


def _swing_high(highs: list[float], lookback: int = 30) -> float:
    return max(highs[-lookback:]) if highs else 0.0


def _swing_low(lows: list[float], lookback: int = 30) -> float:
    return min(lows[-lookback:]) if lows else 0.0


def _pip_size(symbol: str) -> float:
    """Return pip size for symbol (0.0001 for most FX, 0.01 for JPY pairs)."""
    if "JPY" in symbol.upper():
        return 0.01
    return 0.0001


# ─────────────────────────────────────────────────────────────────────────────
# Session Awareness
# ─────────────────────────────────────────────────────────────────────────────

SESSIONS = {
    "tokyo":   (0,  9),    # 00:00–09:00 UTC
    "london":  (7,  16),   # 07:00–16:00 UTC
    "new_york":(12, 21),   # 12:00–21:00 UTC
}

# Which sessions are high-probability for which pairs
PAIR_SESSIONS: Dict[str, List[str]] = {
    "EUR_USD": ["london", "new_york"],
    "GBP_USD": ["london", "new_york"],
    "USD_JPY": ["tokyo", "london", "new_york"],
    "USD_CHF": ["london", "new_york"],
    "AUD_USD": ["tokyo", "london"],
    "NZD_USD": ["tokyo", "london"],
    "USD_CAD": ["new_york", "london"],
    "GBP_JPY": ["tokyo", "london"],
    "EUR_JPY": ["tokyo", "london"],
    "XAU_USD": ["london", "new_york"],
}
_DEFAULT_SESSIONS = ["london", "new_york"]


def session_bias(symbol: str, utc_now: Optional[datetime] = None) -> Tuple[str, float]:
    """
    Returns (active_session_name, confidence_multiplier).
    Multiplier: 1.0 = prime session, 0.70 = off-session (still tradeable but
    confidence is dampened so only genuinely strong setups survive the gate).
    """
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    h = utc_now.hour
    preferred = PAIR_SESSIONS.get(symbol.upper(), _DEFAULT_SESSIONS)

    active = []
    for name, (start, end) in SESSIONS.items():
        if start <= h < end:
            active.append(name)
    # overlap = London+NY (07–16 UTC) is highest quality
    if len(active) >= 2:
        return ("overlap", 1.0)
    for sess in active:
        if sess in preferred:
            return (sess, 1.0)
    if active:
        return (active[0], 0.80)
    return ("off_session", 0.70)


# ─────────────────────────────────────────────────────────────────────────────
# Signal result type
# ─────────────────────────────────────────────────────────────────────────────

class SignalResult:
    def __init__(
        self,
        detector: str,
        direction: Optional[str],   # "BUY" | "SELL" | None
        confidence: float,
        entry: float,
        sl: float,
        tp: float,
        meta: Dict[str, Any],
    ):
        self.detector = detector
        self.direction = direction
        self.confidence = round(confidence, 4)
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.rr = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 1e-9 else 0.0
        self.meta = meta

    def as_dict(self) -> dict:
        return {
            "detector": self.detector,
            "direction": self.direction,
            "confidence": self.confidence,
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "rr": round(self.rr, 2),
            "meta": self.meta,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Momentum SMA Detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_momentum_sma(symbol: str, candles: list) -> Optional[SignalResult]:
    closes = _closes(candles)[-100:]
    if len(closes) < 52:
        return None
    s20 = _sma(closes, 20)
    s50 = _sma(closes, 50)
    roc = _roc(closes, 10)
    pip = _pip_size(symbol)
    price = closes[-1]

    direction = None
    if s20 > s50 and roc > 0.15:
        direction = "BUY"
    elif s20 < s50 and roc < -0.15:
        direction = "SELL"
    if direction is None:
        return None

    conf = min(0.90, abs(roc) / 2.0)
    sl_dist = 10 * pip
    tp_dist = 30 * pip
    if direction == "BUY":
        sl, tp = price - sl_dist, price + tp_dist
    else:
        sl, tp = price + sl_dist, price - tp_dist

    return SignalResult("momentum_sma", direction, conf, price, sl, tp,
                        {"sma20": s20, "sma50": s50, "roc": roc})


# ─────────────────────────────────────────────────────────────────────────────
# 2. EMA Stack Detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_ema_stack(symbol: str, candles: list) -> Optional[SignalResult]:
    closes = _closes(candles)[-120:]
    if len(closes) < 60:
        return None
    e8  = _ema(closes, 8)
    e21 = _ema(closes, 21)
    e55 = _ema(closes, 55)
    price = closes[-1]
    pip = _pip_size(symbol)

    # Bullish: price > e8 > e21 > e55 (stack)
    # Bearish: price < e8 < e21 < e55
    if price > e8 > e21 > e55:
        direction = "BUY"
        sep = (e8 - e55) / e55 * 100   # stack separation %
        conf = min(0.88, 0.55 + sep * 5)
    elif price < e8 < e21 < e55:
        direction = "SELL"
        sep = (e55 - e8) / e55 * 100
        conf = min(0.88, 0.55 + sep * 5)
    else:
        return None

    sl_dist = 12 * pip
    tp_dist = 36 * pip
    if direction == "BUY":
        sl, tp = price - sl_dist, price + tp_dist
    else:
        sl, tp = price + sl_dist, price - tp_dist

    return SignalResult("ema_stack", direction, conf, price, sl, tp,
                        {"ema8": e8, "ema21": e21, "ema55": e55})


# ─────────────────────────────────────────────────────────────────────────────
# 3. Fair Value Gap (FVG) Detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_fvg(symbol: str, candles: list) -> Optional[SignalResult]:
    """
    Bullish FVG: candle[i].low > candle[i+2].high  (gap left above)
    Bearish FVG: candle[i].high < candle[i+2].low  (gap left below)
    Price then pulls back INTO the gap → high-probability continuation.
    """
    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)
    if len(closes) < 10 or len(highs) < 10 or len(lows) < 10:
        return None

    price = closes[-1]
    pip   = _pip_size(symbol)
    best: Optional[SignalResult] = None

    # Scan last 20 candles for FVG zones, pick most recent unfilled one
    n = min(len(closes), 20)
    for i in range(len(closes) - n, len(closes) - 2):
        h0, l0 = highs[i], lows[i]
        h2, l2 = highs[i + 2], lows[i + 2]

        # Bullish FVG
        if l0 > h2:
            gap_top, gap_bot = l0, h2
            gap_size = gap_top - gap_bot
            # Price is retesting inside the gap
            if gap_bot <= price <= gap_top:
                # Strength = gap size relative to pip
                strength = gap_size / pip
                conf = min(0.85, 0.55 + strength * 0.01)
                sl = gap_bot - 3 * pip
                tp = price + 3 * gap_size   # ~3R extension
                r = SignalResult("fvg", "BUY", conf, price, sl, tp,
                                 {"gap_top": gap_top, "gap_bot": gap_bot,
                                  "gap_pips": round(strength, 1), "type": "bullish_fvg"})
                if best is None or conf > best.confidence:
                    best = r

        # Bearish FVG
        elif h0 < l2:
            gap_top, gap_bot = l2, h0
            gap_size = gap_top - gap_bot
            if gap_bot <= price <= gap_top:
                strength = gap_size / pip
                conf = min(0.85, 0.55 + strength * 0.01)
                sl = gap_top + 3 * pip
                tp = price - 3 * gap_size
                r = SignalResult("fvg", "SELL", conf, price, sl, tp,
                                 {"gap_top": gap_top, "gap_bot": gap_bot,
                                  "gap_pips": round(strength, 1), "type": "bearish_fvg"})
                if best is None or conf > best.confidence:
                    best = r

    return best


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fibonacci Retracement Detector
# ─────────────────────────────────────────────────────────────────────────────

FIB_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786]
KEY_FIBS   = {0.500, 0.618, 0.786}   # higher bonus


def detect_fibonacci(symbol: str, candles: list) -> Optional[SignalResult]:
    """
    Identify swing H/L over last 50 candles.
    Check if current price is within tolerance of a key fib retracement.
    Use EMA55 trend bias to determine direction.
    """
    highs  = _highs(candles)[-50:]
    lows   = _lows(candles)[-50:]
    closes = _closes(candles)[-60:]
    if len(closes) < 55:
        return None

    price  = closes[-1]
    pip    = _pip_size(symbol)
    sh     = _swing_high(highs, 50)
    sl_    = _swing_low(lows, 50)
    swing  = sh - sl_
    if swing < 10 * pip:   # too small a swing to be meaningful
        return None

    # Trend bias from EMA55
    e55 = _ema(closes, 55)
    trend_up = price > e55

    tol = 0.003   # within 0.3% of price counts as "at fib"

    best_dist = float("inf")
    best_lvl  = None
    best_fib_price = None

    for lvl in FIB_LEVELS:
        # In uptrend: retracement = bull pull-back = sh - swing*lvl
        # In downtrend: retracement = bear pull-back = sl_ + swing*lvl
        if trend_up:
            fib_price = sh - swing * lvl
        else:
            fib_price = sl_ + swing * lvl

        dist = abs(price - fib_price) / price
        if dist < best_dist:
            best_dist = dist
            best_lvl  = lvl
            best_fib_price = fib_price

    if best_dist > tol:
        return None

    direction = "BUY" if trend_up else "SELL"
    proximity_score = 1.0 - (best_dist / tol)
    bonus = 0.15 if best_lvl in KEY_FIBS else 0.0
    conf  = min(0.90, 0.55 + proximity_score * 0.25 + bonus)

    if direction == "BUY":
        sl = sl_ - 3 * pip
        tp = sh + swing * 0.272    # extension toward 1.272
    else:
        sl = sh + 3 * pip
        tp = sl_ - swing * 0.272

    return SignalResult("fibonacci", direction, conf, price, sl, tp,
                        {"fib_level": best_lvl, "fib_price": round(best_fib_price, 5),
                         "swing_high": round(sh, 5), "swing_low": round(sl_, 5),
                         "distance_pct": round(best_dist * 100, 3)})


# ─────────────────────────────────────────────────────────────────────────────
# 5. Liquidity Sweep Detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_liquidity_sweep(symbol: str, candles: list) -> Optional[SignalResult]:
    """
    Equal highs (within 2 pips) swept then reversed → SELL.
    Equal lows swept then recovered → BUY.
    Requires a bullish/bearish close AFTER the sweep candle.
    """
    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)
    if len(closes) < 15:
        return None

    pip   = _pip_size(symbol)
    price = closes[-1]
    tol   = 2 * pip

    # Check last 3 candles for sweep
    h3 = highs[-4:-1]
    l3 = lows[-4:-1]
    c3 = closes[-4:-1]

    # Equal-highs sweep → bear reversal
    max_h = max(h3)
    prev_h_avg = sum(h3[:-1]) / max(len(h3[:-1]), 1)
    if abs(max_h - prev_h_avg) < tol and highs[-1] > max_h and closes[-1] < highs[-1]:
        # wick spiked above equal highs then closed lower → sweep + reversal
        conf = 0.72
        sl   = highs[-1] + 3 * pip
        tp   = price - (sl - price) * 3
        return SignalResult("liq_sweep", "SELL", conf, price, sl, tp,
                            {"type": "equal_highs_sweep", "swept": round(max_h, 5)})

    # Equal-lows sweep → bull reversal
    min_l = min(l3)
    prev_l_avg = sum(l3[:-1]) / max(len(l3[:-1]), 1)
    if abs(min_l - prev_l_avg) < tol and lows[-1] < min_l and closes[-1] > lows[-1]:
        conf = 0.72
        sl   = lows[-1] - 3 * pip
        tp   = price + (price - sl) * 3
        return SignalResult("liq_sweep", "BUY", conf, price, sl, tp,
                            {"type": "equal_lows_sweep", "swept": round(min_l, 5)})

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Trap Reversal (Pin Bar / Engulfing) Detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_trap_reversal(symbol: str, candles: list) -> Optional[SignalResult]:
    """
    Bearish pin bar at recent swing high → SELL trap.
    Bullish pin bar at recent swing low → BUY trap.
    Also catches bullish/bearish engulfing.
    """
    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)
    if len(closes) < 20:
        return None

    pip   = _pip_size(symbol)
    price = closes[-1]

    # Get last candle OHLC
    c1 = candles[-1]
    if not isinstance(c1, dict):
        return None

    def _v(c, keys) -> float:
        for k in keys:
            v = c.get("mid", {}).get(k) or c.get(k)
            if v:
                return float(v)
        return 0.0

    o1 = _v(c1, ["o", "open"])
    h1 = _v(c1, ["h", "high"])
    l1 = _v(c1, ["l", "low"])
    c_close = closes[-1]
    if not all([o1, h1, l1, c_close]):
        return None

    body = abs(c_close - o1)
    full_range = h1 - l1 if h1 > l1 else 1e-9
    upper_wick  = h1 - max(o1, c_close)
    lower_wick  = min(o1, c_close) - l1
    body_ratio  = body / full_range

    sh = _swing_high(highs, 20)
    sl_ = _swing_low(lows, 20)
    at_high = abs(price - sh) < 10 * pip
    at_low  = abs(price - sl_) < 10 * pip

    # Bearish pin bar at high
    if at_high and upper_wick > 2 * body and body_ratio < 0.35:
        conf = 0.68 + min(0.15, (upper_wick / full_range) * 0.3)
        sl   = h1 + 3 * pip
        tp   = price - (sl - price) * 3
        return SignalResult("trap_reversal", "SELL", conf, price, sl, tp,
                            {"pattern": "bearish_pin_bar",
                             "upper_wick_pips": round(upper_wick / pip, 1)})

    # Bullish pin bar at low
    if at_low and lower_wick > 2 * body and body_ratio < 0.35:
        conf = 0.68 + min(0.15, (lower_wick / full_range) * 0.3)
        sl   = l1 - 3 * pip
        tp   = price + (price - sl) * 3
        return SignalResult("trap_reversal", "BUY", conf, price, sl, tp,
                            {"pattern": "bullish_pin_bar",
                             "lower_wick_pips": round(lower_wick / pip, 1)})

    # Bullish engulfing
    if len(candles) >= 2:
        prev_c = closes[-2]
        prev_h = highs[-2] if len(highs) >= 2 else 0
        if (c_close > o1                         # bullish close
                and o1 < prev_c                  # opened below prior close
                and c_close > prev_h             # closed above prior high
                and at_low):
            conf = 0.70
            sl   = l1 - 3 * pip
            tp   = price + (price - sl) * 3
            return SignalResult("trap_reversal", "BUY", conf, price, sl, tp,
                                {"pattern": "bullish_engulfing"})

    # Bearish engulfing
    if len(candles) >= 2:
        prev_c = closes[-2]
        prev_l = lows[-2] if len(lows) >= 2 else float("inf")
        if (c_close < o1                         # bearish close
                and o1 > prev_c                  # opened above prior close
                and c_close < prev_l             # closed below prior low
                and at_high):
            conf = 0.70
            sl   = h1 + 3 * pip
            tp   = price - (sl - price) * 3
            return SignalResult("trap_reversal", "SELL", conf, price, sl, tp,
                                {"pattern": "bearish_engulfing"})

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 7. RSI Divergence + Oversold/Overbought
# ─────────────────────────────────────────────────────────────────────────────

def _rsi(closes: list[float], n: int = 14) -> float:
    if len(closes) < n + 1:
        return 50.0
    gains, losses = [], []
    for i in range(len(closes) - n, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains) / n; al = sum(losses) / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - 100 / (1 + rs)


def detect_rsi_extremes(symbol: str, candles: list) -> Optional[SignalResult]:
    closes = _closes(candles)[-80:]
    if len(closes) < 20:
        return None
    rsi_now  = _rsi(closes, 14)
    rsi_prev = _rsi(closes[:-5], 14)
    pip      = _pip_size(symbol)
    price    = closes[-1]

    if rsi_now < 28:  # oversold
        # divergence bonus: price lower but RSI higher
        div_bonus = 0.10 if rsi_now > rsi_prev else 0.0
        conf = min(0.80, 0.55 + (28 - rsi_now) * 0.01 + div_bonus)
        sl   = price - 12 * pip
        tp   = price + 36 * pip
        return SignalResult("rsi_extreme", "BUY", conf, price, sl, tp,
                            {"rsi": round(rsi_now, 2), "type": "oversold",
                             "divergence": div_bonus > 0})

    if rsi_now > 72:  # overbought
        div_bonus = 0.10 if rsi_now < rsi_prev else 0.0
        conf = min(0.80, 0.55 + (rsi_now - 72) * 0.01 + div_bonus)
        sl   = price + 12 * pip
        tp   = price - 36 * pip
        return SignalResult("rsi_extreme", "SELL", conf, price, sl, tp,
                            {"rsi": round(rsi_now, 2), "type": "overbought",
                             "divergence": div_bonus > 0})

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Signal Aggregator
# ─────────────────────────────────────────────────────────────────────────────

DETECTORS = [
    detect_momentum_sma,
    detect_ema_stack,
    detect_fvg,
    detect_fibonacci,
    detect_liquidity_sweep,
    detect_trap_reversal,
    detect_rsi_extremes,
]

# Minimum individual confidence to count as a "vote"
_MIN_VOTE_CONF = 0.55
# Minimum votes in the same direction to fire a trade
_MIN_VOTES = 2


class AggregatedSignal:
    """Final result returned to the trading engine."""
    def __init__(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        entry: float,
        sl: float,
        tp: float,
        votes: int,
        detectors_fired: List[str],
        all_results: List[SignalResult],
        session: str,
        session_mult: float,
    ):
        self.symbol         = symbol
        self.direction      = direction
        self.confidence     = round(confidence, 4)
        self.entry          = entry
        self.sl             = sl
        self.tp             = tp
        # ── Store raw pip distances so place_trade can rebase to live price ──
        self.risk_dist      = abs(sl - entry)    # distance entry→SL in price
        self.reward_dist    = abs(tp - entry)    # distance entry→TP in price
        self.rr             = self.reward_dist / self.risk_dist if self.risk_dist > 1e-9 else 0.0
        self.votes          = votes
        self.detectors_fired = detectors_fired
        self.all_results    = all_results
        self.session        = session
        self.session_mult   = session_mult

    def as_dict(self) -> dict:
        return {
            "symbol":          self.symbol,
            "direction":       self.direction,
            "confidence":      self.confidence,
            "entry":           self.entry,
            "sl":              self.sl,
            "tp":              self.tp,
            "rr":              round(self.rr, 2),
            "votes":           self.votes,
            "detectors":       self.detectors_fired,
            "session":         self.session,
            "session_mult":    self.session_mult,
        }


def scan_symbol(
    symbol: str,
    candles: list,
    utc_now: Optional[datetime] = None,
    min_confidence: float = 0.76,
    min_votes: int = _MIN_VOTES,
) -> Optional[AggregatedSignal]:
    """
    Run all detectors on `candles` for `symbol`.
    Return the best AggregatedSignal if enough detectors agree,
    or None if there is no tradeable setup.

    The winning direction is decided by VOTE COUNT first,
    then TIE-BREAK by highest confidence sum.
    """
    session_name, session_mult = session_bias(symbol, utc_now)

    # Run every detector, collect results
    all_results: List[SignalResult] = []
    for fn in DETECTORS:
        try:
            r = fn(symbol, candles)
            if r and r.confidence >= _MIN_VOTE_CONF and r.direction:
                all_results.append(r)
        except Exception:
            pass  # one detector failing must never kill the scan

    if not all_results:
        return None

    # Group by direction
    by_dir: Dict[str, List[SignalResult]] = {}
    for r in all_results:
        by_dir.setdefault(r.direction, []).append(r)

    # Pick direction with most votes, tie-break by sum of confidence
    best_dir = max(by_dir, key=lambda d: (len(by_dir[d]),
                                          sum(r.confidence for r in by_dir[d])))
    voted = by_dir[best_dir]
    if len(voted) < min_votes:
        return None

    # Aggregate SL/TP:
    #   SL: most conservative (furthest from entry) for safety
    #   TP: most aggressive (furthest from entry) for reward
    #   Entry: last close (market order)
    entry = voted[0].entry  # all share same candle close
    if best_dir == "BUY":
        sl = min(r.sl for r in voted)   # lowest SL protects most
        tp = max(r.tp for r in voted)   # highest TP aims highest
    else:
        sl = max(r.sl for r in voted)   # highest SL for short
        tp = min(r.tp for r in voted)   # lowest TP aims lowest

    # Weighted confidence = mean of voting detectors × session multiplier
    raw_conf = sum(r.confidence for r in voted) / len(voted)
    final_conf = min(0.99, raw_conf * session_mult)

    if final_conf < min_confidence:
        return None

    return AggregatedSignal(
        symbol          = symbol,
        direction       = best_dir,
        confidence      = final_conf,
        entry           = entry,
        sl              = sl,
        tp              = tp,
        votes           = len(voted),
        detectors_fired = [r.detector for r in voted],
        all_results     = all_results,
        session         = session_name,
        session_mult    = session_mult,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Incremental Position Management
# ─────────────────────────────────────────────────────────────────────────────

class TradeAction:
    HOLD           = "HOLD"
    SCALE_OUT_HALF = "SCALE_OUT_HALF"   # close 50% at 1R
    TRAIL_TIGHT    = "TRAIL_TIGHT"      # tighten trail at 2R
    CLOSE_ALL      = "CLOSE_ALL"        # full exit
    MOVE_BE        = "MOVE_BE"          # move SL to breakeven


def manage_open_trade(
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    current_price: float,
    symbol: str,
    scaled_out: bool = False,
    trail_active: bool = False,
    session: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Given current price on an open trade, returns (action, detail_dict).

    Logic:
      • 0.5R profit  → Move SL to breakeven
      • 1.0R profit  → Scale out 50% (if not already done)
      • 2.0R profit  → Activate tight trail (trail at 0.3R behind)
      • Price crosses back through prior trail level → Close all
      • Session ends (off_session) → Close all (prevent overnight drift)
    """
    risk = abs(entry - sl)
    if risk < 1e-9:
        return (TradeAction.HOLD, {})

    if direction == "BUY":
        pnl_r = (current_price - entry) / risk
    else:
        pnl_r = (entry - current_price) / risk

    detail: Dict[str, Any] = {
        "pnl_r": round(pnl_r, 3),
        "current": current_price,
        "entry": entry,
        "sl": sl,
    }

    # Session ended → protect profits
    if session == "off_session" and pnl_r > 0.5:
        detail["reason"] = "session_ended_with_profit"
        return (TradeAction.CLOSE_ALL, detail)

    # Already losing beyond SL (staleness guard)
    if pnl_r < -1.05:
        detail["reason"] = "stop_breach"
        return (TradeAction.CLOSE_ALL, detail)

    # 2R+ → tight trail
    if pnl_r >= 2.0 and not trail_active:
        detail["reason"] = "2R_trail_activate"
        detail["new_sl"] = current_price - 0.3 * risk if direction == "BUY" \
                           else current_price + 0.3 * risk
        return (TradeAction.TRAIL_TIGHT, detail)

    # 1R → scale out
    if pnl_r >= 1.0 and not scaled_out:
        detail["reason"] = "1R_scale_out"
        return (TradeAction.SCALE_OUT_HALF, detail)

    # 0.5R → move to breakeven
    if pnl_r >= 0.5:
        detail["reason"] = "0.5R_breakeven"
        detail["new_sl"] = entry
        return (TradeAction.MOVE_BE, detail)

    return (TradeAction.HOLD, detail)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrapper — drop-in replacement for momentum_signals.generate_signal
# ─────────────────────────────────────────────────────────────────────────────

def generate_signal(symbol: str, candles: list):
    """
    Backward-compatible wrapper.
    Returns (signal, confidence, meta) 3-tuple.
    """
    result = scan_symbol(symbol, candles)
    if result is None:
        return (None, 0.0, {"reason": "no_edge"})
    return (
        result.direction,
        result.confidence,
        {
            "detectors": result.detectors_fired,
            "votes":     result.votes,
            "session":   result.session,
            "rr":        round(result.rr, 2),
            "sl":        result.sl,
            "tp":        result.tp,
        },
    )
