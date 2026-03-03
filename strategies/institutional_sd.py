from __future__ import annotations
from typing import Optional, List, Dict

from .base import BaseStrategy, StrategyContext, ProposedTrade

def _f(c, *keys) -> float:
    for k in keys:
        v = c.get(k)
        if v is not None: return float(v)
    return 0.0

def _ohlc(candles):
    O, H, L, C = [], [], [], []
    for c in candles:
        if not isinstance(c, dict): continue
        O.append(_f(c,"open","o")); H.append(_f(c,"high","h"))
        L.append(_f(c,"low","l"));  C.append(_f(c,"close","c"))
    return O, H, L, C

def _pip(sym): return 0.01 if "JPY" in sym.upper() else 0.0001
def _ema(seq, n):
    if not seq: return 0.0
    k = 2.0/(n+1); v = seq[0]
    for p in seq[1:]: v = p*k + v*(1-k)
    return v


def _detect_sd_zones(highs, lows, closes, opens, lookback=60, min_move_mult=2.0):
    """
    Detect Supply and Demand zones from raw candles.

    Supply zone  (institutional selling area):
      A base of     candling  (bodies < 30% of avg body) followed by a strong
      bearish impulse (close drops ≥ min_move_mult × avg_body).
      The zone = the range of the base candle(s) before the impulse.

    Demand zone  (institutional buying area):  mirror.

    Returns: {"demand": [...], "supply": [...]}
    each zone: {"lower": float, "upper": float, "fresh": bool, "origin_idx": int}
    """
    if len(closes) < lookback + 5:
        return {"demand": [], "supply": []}

    slice_o = opens[-lookback:]
    slice_h = highs[-lookback:]
    slice_l = lows[-lookback:]
    slice_c = closes[-lookback:]

    bodies = [abs(slice_c[i] - slice_o[i]) for i in range(len(slice_c))]
    avg_body = sum(bodies) / max(len(bodies), 1) if bodies else 1e-9

    demand_zones: List[Dict] = []
    supply_zones: List[Dict] = []

    for i in range(len(slice_c) - 3):
        body_i = abs(slice_c[i] - slice_o[i])
        # Base candle: indecision (small body)
        if body_i > 0.5 * avg_body:
            continue

        # Next candle: strong impulse
        impulse_body = abs(slice_c[i+1] - slice_o[i+1])
        if impulse_body < min_move_mult * avg_body:
            continue

        # Demand: base then bullish impulse
        if slice_c[i+1] > slice_o[i+1]:   # bullish impulse
            lower = slice_l[i]
            upper = max(slice_o[i], slice_c[i])
            if upper <= lower: upper = lower + avg_body
            # Fresh = price has not traded back into zone since formation
            fresh = not any(slice_l[j] < upper for j in range(i+2, len(slice_l)))
            demand_zones.append({"lower": lower, "upper": upper, "fresh": fresh,
                                  "origin_idx": i, "strength": impulse_body / avg_body})

        # Supply: base then bearish impulse
        elif slice_c[i+1] < slice_o[i+1]:  # bearish impulse
            upper = slice_h[i]
            lower = min(slice_o[i], slice_c[i])
            if lower >= upper: lower = upper - avg_body
            fresh = not any(slice_h[j] > lower for j in range(i+2, len(slice_h)))
            supply_zones.append({"lower": lower, "upper": upper, "fresh": fresh,
                                  "origin_idx": i, "strength": impulse_body / avg_body})

    return {"demand": demand_zones, "supply": supply_zones}


class InstitutionalSupplyDemandStrategy(BaseStrategy):
    """
    Institutional Supply & Demand — zone detection from raw candles.

    Methodology:
      1. Scan last 60 candles for "base + impulse" S&D zone formations.
         Base  = indecision candle (small body ≤ 50 % of avg body)
         Impulse = the next candle body ≥ 2 × avg body (institutional fuel)
      2. Price must retrace INTO a fresh zone (zone not yet revisited).
      3. EMA55 provides higher-timeframe trend bias:
           price above EMA55 → look for demand zones (BUY)
           price below EMA55 → look for supply zones (SELL)
      4. Entry:  market order on retest
         SL:     beyond the zone (1 pip buffer below lower / above upper)
         TP:     target_rr × risk (toward prior impulse high/low)

    Confidence scales with zone strength (impulse magnitude).
    """

    def decide_entry(self, ctx: StrategyContext) -> Optional[ProposedTrade]:
        if ctx.timeframe not in self.metadata.base_timeframes:
            return None
        if len(ctx.candles) < 70:
            return None

        O, H, L, C = _ohlc(ctx.candles)
        pip   = _pip(ctx.symbol)
        price = C[-1]
        ema55 = _ema(C[-70:], 55)

        zones = _detect_sd_zones(H, L, C, O, lookback=60)

        # ── BUY: price in fresh demand zone, above EMA55 ──────────────────────
        if price > ema55:
            for z in sorted(zones["demand"], key=lambda x: -x["strength"]):
                if not z["fresh"]:
                    continue
                if z["lower"] <= price <= z["upper"]:
                    sl_   = z["lower"] - 2 * pip
                    risk  = price - sl_
                    if risk <= 0: continue
                    tp    = price + risk * self.metadata.target_rr
                    conf  = min(0.90, 0.68 + min(z["strength"] * 0.04, 0.18))
                    return ProposedTrade(
                        strategy_code=self.metadata.code, symbol=ctx.symbol,
                        direction="BUY", entry_type="market", entry_price=None,
                        stop_loss_price=round(sl_,5), take_profit_price=round(tp,5),
                        target_rr=self.metadata.target_rr, confidence=conf,
                        notes={"reason":"demand_zone_retest",
                               "zone_lower":round(z["lower"],5),
                               "zone_upper":round(z["upper"],5),
                               "strength":round(z["strength"],2),
                               "ema55":round(ema55,5)})

        # ── SELL: price in fresh supply zone, below EMA55 ─────────────────────
        if price < ema55:
            for z in sorted(zones["supply"], key=lambda x: -x["strength"]):
                if not z["fresh"]:
                    continue
                if z["lower"] <= price <= z["upper"]:
                    sl_   = z["upper"] + 2 * pip
                    risk  = sl_ - price
                    if risk <= 0: continue
                    tp    = price - risk * self.metadata.target_rr
                    conf  = min(0.90, 0.68 + min(z["strength"] * 0.04, 0.18))
                    return ProposedTrade(
                        strategy_code=self.metadata.code, symbol=ctx.symbol,
                        direction="SELL", entry_type="market", entry_price=None,
                        stop_loss_price=round(sl_,5), take_profit_price=round(tp,5),
                        target_rr=self.metadata.target_rr, confidence=conf,
                        notes={"reason":"supply_zone_retest",
                               "zone_lower":round(z["lower"],5),
                               "zone_upper":round(z["upper"],5),
                               "strength":round(z["strength"],2),
                               "ema55":round(ema55,5)})

        return None
