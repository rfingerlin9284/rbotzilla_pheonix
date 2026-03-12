
import os
import logging
from systems.multi_signal_engine import scan_symbol

logger = logging.getLogger(__name__)

class StrategyAggregator:
    """
    Wraps the Multi-Signal Engine to act as the StrategyAggregator 
    expected by the OandaTradingEngine.
    """
    def __init__(self, signal_vote_threshold=2):
        self.signal_vote_threshold = signal_vote_threshold
        logger.info(f"✅ StrategyAggregator (Multi-Signal Wrapper) loaded with threshold {signal_vote_threshold}")

    def get_signal(self, symbol, candles):
        """
        Polls the multi-signal engine for a consensus signal.
        """
        # scan_symbol returns an AggregatedSignal object (or dict)
        result = scan_symbol(symbol, candles)
        
        # If result exists and meets our threshold, return it
        if result and getattr(result, 'confidence', 0) >= 0.68:
            return result
        
        return None
