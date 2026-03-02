"""
Strategy Registry — single source of truth for all active strategies.
Each entry wires a StrategyMetadata + class together.
Import `STRATEGY_REGISTRY` to get all live strategies.
"""
from __future__ import annotations
from typing import List

from .base import BaseStrategy, StrategyMetadata

from .liquidity_sweep          import LiquiditySweepReversalStrategy
from .trap_reversal_scalper    import TrapReversalScalperStrategy
from .fib_confluence_breakout  import FibConfluenceBreakoutStrategy
from .price_action_holy_grail  import PriceActionHolyGrailStrategy
from .institutional_sd         import InstitutionalSupplyDemandStrategy
from .bullish_wolf              import BullishWolf
from .bearish_wolf              import BearishWolf
from .sideways_wolf             import SidewaysWolf
from .crypto_breakout          import CryptoBreakoutStrategy


def _fx(code, name, priority, tfs, max_hold, rr, wr) -> StrategyMetadata:
    return StrategyMetadata(
        name=name, code=code, priority=priority,
        markets=["FX"], base_timeframes=tfs,
        max_hold_minutes=max_hold, target_rr=rr, est_win_rate=wr,
    )


_DEFS: List[tuple[StrategyMetadata, type]] = [
    # ── Tier 1 — gold: highest edge, institutional alignment ─────────────────
    (
        _fx("INST_SD",   "Institutional Supply & Demand",  "gold",
            ["M15","H1"], 240, 3.5, 0.58),
        InstitutionalSupplyDemandStrategy,
    ),
    (
        _fx("LIQ_SWEEP", "Liquidity Sweep Reversal",       "gold",
            ["M5","M15"], 120, 3.2, 0.56),
        LiquiditySweepReversalStrategy,
    ),
    (
        _fx("TRAP_REV",  "Trap Reversal Scalper",          "gold",
            ["M5","M15"], 90,  3.2, 0.55),
        TrapReversalScalperStrategy,
    ),
    (
        _fx("HOLY_GRAIL","Price Action Holy Grail",        "gold",
            ["M15","H1"], 180, 3.0, 0.54),
        PriceActionHolyGrailStrategy,
    ),

    # ── Tier 2 — silver: good edge, slightly noisier ─────────────────────────
    (
        _fx("FIB_BRK",   "Fibonacci Confluence Breakout",  "silver",
            ["M15","H1"], 240, 3.5, 0.52),
        FibConfluenceBreakoutStrategy,
    ),
    (
        StrategyMetadata(
            name="Crypto / Vol Breakout", code="CRYPTO_BRK", priority="silver",
            markets=["FX","CRYPTO"], base_timeframes=["M15","H1"],
            max_hold_minutes=180, target_rr=3.2, est_win_rate=0.50,
        ),
        CryptoBreakoutStrategy,
    ),

    # ── Tier 3 — bronze: regime-specific wolves (BullishWolf / BearishWolf use
    #    their own pandas-based logic; wrap them to fit BaseStrategy interface) ─
]


def _wolf_wrapper(wolf_cls, code, name, priority, tfs, rr, wr) -> tuple:
    """Thin adapter: BullishWolf / BearishWolf don't extend BaseStrategy."""
    meta = _fx(code, name, priority, tfs, 120, rr, wr)
    # Return None class — these are invoked separately via wolf_pack_runner
    return (meta, None, wolf_cls)


WOLF_PACK = [
    _wolf_wrapper(BullishWolf,  "BULL_WOLF", "Bullish Wolf Pack",  "bronze", ["M15","H1"], 3.0, 0.50),
    _wolf_wrapper(BearishWolf,  "BEAR_WOLF", "Bearish Wolf Pack",  "bronze", ["M15","H1"], 3.0, 0.50),
    _wolf_wrapper(SidewaysWolf, "SIDE_WOLF", "Sideways Wolf Pack", "bronze", ["M15","H1"], 2.5, 0.48),
]

# Main registry: (metadata, instantiated_strategy) pairs
STRATEGY_REGISTRY: List[tuple[StrategyMetadata, BaseStrategy]] = []
for _meta, _cls in _DEFS:
    try:
        STRATEGY_REGISTRY.append((_meta, _cls(_meta)))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to init strategy {_meta.code}: {e}")


def get_strategies_for_timeframe(tf: str) -> List[tuple[StrategyMetadata, BaseStrategy]]:
    return [(m, s) for m, s in STRATEGY_REGISTRY if tf in m.base_timeframes]


def get_gold_tier() -> List[tuple[StrategyMetadata, BaseStrategy]]:
    return [(m, s) for m, s in STRATEGY_REGISTRY if m.priority == "gold"]


def describe() -> None:
    print(f"\n{'CODE':12} {'PRIORITY':8} {'TFs':15} {'RR':5} {'WIN%':6} {'NAME'}")
    print("-" * 75)
    for m, _ in STRATEGY_REGISTRY:
        tfs = ",".join(m.base_timeframes)
        print(f"{m.code:12} {m.priority:8} {tfs:15} {m.target_rr:<5.1f} "
              f"{m.est_win_rate*100:<6.0f} {m.name}")
    print()


if __name__ == "__main__":
    describe()
