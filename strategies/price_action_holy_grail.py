from __future__ import annotations
from typing import Optional

from .base import BaseStrategy, StrategyContext, ProposedTrade

def _f(c, *keys) -> float:
    for k in keys:
        v = c.get(k)
        if v is not None: return float(v)
    return 0.0

def _ohlc(candles):
    H, L, C = [], [], []
    for c in candles:
        if not isinstance(c, dict): continue
        H.append(_f(c,"high","h")); L.append(_f(c,"low","l")); C.append(_f(c,"close","c"))
    return H, L, C

def _pip(sym): return 0.01 if "JPY" in sym.upper() else 0.0001
def _ema(seq, n):
    if not seq: return 0.0
    k = 2.0/(n+1); v = seq[0]
    for p in seq[1:]: v = p*k + v*(1-k)
    return v
def _rsi(closes, n=14) -> float:
    if len(closes) < n+1: return 50.0
    gains, losses = [], []
    for i in range(len(closes)-n, len(closes)):
        d = closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag = sum(gains)/n; al = sum(losses)/n
    if al == 0: return 100.0
    return 100 - 100/(1+ag/al)


class PriceActionHolyGrailStrategy(BaseStrategy):
    """
    Price Action Holy Grail — EMA21 pull-back with momentum confirmation.

    Classic "Holy Grail" as documented by Linda Bradford Raschke:
      • Market trending above EMA21 (BUY setup) or below (SELL setup)
      • RSI dips to 40-50 zone (pull-back into moving average area) for BUY
        or rises to 50-60 zone for SELL
      • Price retests the EMA21 band (within 5 pips)
      • Confirmation: last candle close BACK in trend direction
      • SL: below the recent swing low (or above swing high for SELL)
      • TP: target_rr × risk, extension toward prior high/low

    Trend strength bonus applied when EMA8 also stacked on correct side.
    """

    def decide_entry(self, ctx: StrategyContext) -> Optional[ProposedTrade]:
        if ctx.timeframe not in self.metadata.base_timeframes:
            return None
        if len(ctx.candles) < 40:
            return None

        H, L, C = _ohlc(ctx.candles)
        pip   = _pip(ctx.symbol)
        price = C[-1]

        ema21 = _ema(C[-40:], 21)
        ema8  = _ema(C[-20:], 8)
        rsi   = _rsi(C[-30:], 14)

        at_ema = abs(price - ema21) <= 5 * pip
        stacked_bull = ema8 > ema21   # EMA8 above EMA21 → strong uptrend
        stacked_bear = ema8 < ema21

        # ── BUY setup ─────────────────────────────────────────────────────────
        # Trend: price was above EMA21 and is pulling back TO it
        # RSI: cooling off to 40-55 range (not oversold, just resting)
        # Confirmation: last close back above EMA21 after touch
        prev_above = any(c > ema21 for c in C[-6:-1])
        if prev_above and at_ema and 38 <= rsi <= 58 and C[-1] > ema21:
            sl_   = min(L[-6:]) - 3 * pip
            risk  = price - sl_
            if risk <= 0: return None
            tp    = price + risk * self.metadata.target_rr
            bonus = 0.08 if stacked_bull else 0.0
            conf  = min(0.88, 0.65 + bonus + max(0, (55-rsi)/15)*0.05)
            return ProposedTrade(
                strategy_code=self.metadata.code, symbol=ctx.symbol,
                direction="BUY", entry_type="market", entry_price=None,
                stop_loss_price=round(sl_,5), take_profit_price=round(tp,5),
                target_rr=self.metadata.target_rr, confidence=conf,
                notes={"reason":"ema21_pullback_buy","rsi":round(rsi,1),
                       "ema21":round(ema21,5),"ema8":round(ema8,5)})

        # ── SELL setup ────────────────────────────────────────────────────────
        prev_below = any(c < ema21 for c in C[-6:-1])
        if prev_below and at_ema and 42 <= rsi <= 62 and C[-1] < ema21:
            sl_   = max(H[-6:]) + 3 * pip
            risk  = sl_ - price
            if risk <= 0: return None
            tp    = price - risk * self.metadata.target_rr
            bonus = 0.08 if stacked_bear else 0.0
            conf  = min(0.88, 0.65 + bonus + max(0, (rsi-45)/15)*0.05)
            return ProposedTrade(
                strategy_code=self.metadata.code, symbol=ctx.symbol,
                direction="SELL", entry_type="market", entry_price=None,
                stop_loss_price=round(sl_,5), take_profit_price=round(tp,5),
                target_rr=self.metadata.target_rr, confidence=conf,
                notes={"reason":"ema21_pullback_sell","rsi":round(rsi,1),
                       "ema21":round(ema21,5),"ema8":round(ema8,5)})

        return None
