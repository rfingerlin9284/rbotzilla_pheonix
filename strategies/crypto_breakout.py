from __future__ import annotations
from typing import Optional

from .base import BaseStrategy, StrategyContext, ProposedTrade

def _f(c, *keys) -> float:
    for k in keys:
        v = c.get(k)
        if v is not None: return float(v)
    return 0.0

def _ohlc(candles):
    H, L, C, V = [], [], [], []
    for c in candles:
        if not isinstance(c, dict): continue
        H.append(_f(c,"high","h")); L.append(_f(c,"low","l"))
        C.append(_f(c,"close","c")); V.append(_f(c,"volume","v"))
    return H, L, C, V

def _ema(seq, n):
    if not seq: return 0.0
    k = 2.0/(n+1); v = seq[0]
    for p in seq[1:]: v = p*k + v*(1-k)
    return v


class CryptoBreakoutStrategy(BaseStrategy):
    """
    Crypto / Volatile-Pair Consolidation Breakout.

    Works on crypto pairs (BTC_USD, ETH_USD) and volatile FX.

    1. Identify a tight consolidation range: last 20 bars where the
       total high-low range is ≤ 1.5 × average 20-bar ATR.
    2. Detect a candle that closes OUTSIDE the range by ≥ 0.3 ATR.
    3. Volume confirmation: breakout candle volume > 1.5 × 20-bar avg.
       (If no volume data available, skip that filter.)
    4. EMA21 on the correct side for trend confirmation.

    SL: opposite edge of the consolidation box + 0.2 ATR buffer.
    TP: target_rr × risk (extension beyond breakout).
    """

    def decide_entry(self, ctx: StrategyContext) -> Optional[ProposedTrade]:
        if ctx.timeframe not in self.metadata.base_timeframes:
            return None
        if len(ctx.candles) < 30:
            return None

        H, L, C, V = _ohlc(ctx.candles)
        price = C[-1]

        # ATR (20-period)
        atrs = []
        for i in range(max(1, len(C)-20), len(C)):
            atrs.append(max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1])))
        atr = sum(atrs)/len(atrs) if atrs else (H[-1]-L[-1])
        if atr == 0: return None

        # Consolidation range: last 20 candles
        box_h = max(H[-20:])
        box_l = min(L[-20:])
        box_range = box_h - box_l

        # Range must be tight: ≤ 1.5 × ATR
        if box_range > 1.5 * atr:
            return None

        ema21 = _ema(C[-30:], 21)

        # Volume check (optional)
        has_vol = any(v > 0 for v in V)
        if has_vol:
            avg_vol = sum(V[-20:])/max(len(V[-20:]),1)
            vol_ok  = V[-1] > 1.5 * avg_vol if avg_vol > 0 else True
        else:
            vol_ok = True

        # ── Bullish breakout ───────────────────────────────────────────────────
        if price > box_h + 0.3 * atr and price > ema21 and vol_ok:
            sl_   = box_l - 0.2 * atr
            risk  = price - sl_
            if risk <= 0: return None
            tp    = price + risk * self.metadata.target_rr
            vol_bonus = 0.07 if has_vol and vol_ok else 0.0
            conf  = min(0.87, 0.68 + (price - box_h) / atr * 0.05 + vol_bonus)
            return ProposedTrade(
                strategy_code=self.metadata.code, symbol=ctx.symbol,
                direction="BUY", entry_type="market", entry_price=None,
                stop_loss_price=round(sl_,5), take_profit_price=round(tp,5),
                target_rr=self.metadata.target_rr, confidence=conf,
                notes={"reason":"bullish_box_breakout","box_h":round(box_h,5),
                       "box_l":round(box_l,5),"atr":round(atr,5),"vol_ok":vol_ok})

        # ── Bearish breakout ───────────────────────────────────────────────────
        if price < box_l - 0.3 * atr and price < ema21 and vol_ok:
            sl_   = box_h + 0.2 * atr
            risk  = sl_ - price
            if risk <= 0: return None
            tp    = price - risk * self.metadata.target_rr
            vol_bonus = 0.07 if has_vol and vol_ok else 0.0
            conf  = min(0.87, 0.68 + (box_l - price) / atr * 0.05 + vol_bonus)
            return ProposedTrade(
                strategy_code=self.metadata.code, symbol=ctx.symbol,
                direction="SELL", entry_type="market", entry_price=None,
                stop_loss_price=round(sl_,5), take_profit_price=round(tp,5),
                target_rr=self.metadata.target_rr, confidence=conf,
                notes={"reason":"bearish_box_breakout","box_h":round(box_h,5),
                       "box_l":round(box_l,5),"atr":round(atr,5),"vol_ok":vol_ok})

        return None
