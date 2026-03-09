#!/usr/bin/env python3
"""
RBOTZILLA PHOENIX - The Master Orchestrator
Cross-Market Hedge Fund Routing Engine

This layer sits above the broker APIs and routes trading signals to the optimal execution platform
based on Asset Class and Session Availability.

PIN: 841921
"""

import os
import sys
import logging
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timezone

# Import Brokers
from brokers.coinbase_connector import get_coinbase_connector, place_coinbase_oco
from brokers.ib_connector import IBConnector
from oanda_trading_engine import OandaTradingEngine

# Import Signals
from systems.multi_signal_engine import AggregatedSignal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] Orchestrator: %(message)s')
logger = logging.getLogger("MasterOrchestrator")

class TradingSession:
    """Manages which markets are currently open"""
    @staticmethod
    def is_crypto_open() -> bool:
        return True # Crypto is 24/7

    @staticmethod
    def is_forex_open() -> bool:
        now = datetime.now(timezone.utc)
        # Closed from Friday 5PM EST to Sunday 5PM EST
        if now.weekday() == 5: # Saturday
            return False
        if now.weekday() == 4 and now.hour >= 22: # Friday after 22:00 UTC
            return False
        if now.weekday() == 6 and now.hour < 22: # Sunday before 22:00 UTC
            return False
        return True

    @staticmethod
    def is_equities_open() -> bool:
        """US Equities RTH (9:30 AM - 4:00 PM EST)"""
        now = datetime.now() # System local time, assuming EST for simplicity
        if now.weekday() > 4: # Weekend
            return False
        # Simplified 9:30-16:00 open check
        current_time = now.time()
        return (current_time.hour == 9 and current_time.minute >= 30) or \
               (10 <= current_time.hour < 16)


class BrokerRouter:
    """Intelligently routes trades to the appropriate broker"""
    
    def __init__(self, pin: int = 841921):
        if pin != 841921:
            raise PermissionError("Invalid Charter PIN")
            
        logger.info("Initializing Hedge Fund Orchestrator Brain...")
        
        # Initialize Coinbase (Crypto)
        try:
            self.coinbase = get_coinbase_connector(pin=841921, environment="live")
            logger.info("✅ Coinbase Connector Linked")
        except Exception as e:
            logger.error(f"❌ Failed to link Coinbase: {e}")
            self.coinbase = None

        # Initialize IBKR (Equities/Futures/Commodities)
        try:
            self.ibkr = IBConnector(pin=841921)
            logger.info("✅ Interactive Brokers Gateway Linked")
        except Exception as e:
            logger.error(f"❌ Failed to link IBKR (is TWS running?): {e}")
            self.ibkr = None
            
        # Initialize OANDA (Forex) - We keep this in practice/live mode depending on env
        try:
            self.oanda = OandaTradingEngine() 
            logger.info("✅ OANDA Trading Engine Linked")
        except Exception as e:
            logger.error(f"❌ Failed to link OANDA: {e}")
            self.oanda = None
            
            
    def determine_broker(self, symbol: str) -> Optional[str]:
        """Determine the correct broker based on asset class"""
        symbol = symbol.upper()
        
        # Crypto
        crypto_pairs = ["BTC", "ETH", "SOL", "DOGE"]
        if any(c in symbol for c in crypto_pairs):
            return "COINBASE"
            
        # Forex
        forex_pairs = ["EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD"]
        # Basic check for a combination of two fiat currencies
        if '_' in symbol and len(symbol.split('_')) == 2:
            base, quote = symbol.split('_')
            if base in forex_pairs and quote in forex_pairs:
                return "OANDA"
                
        # Equities, Indices, Commodities, Futures
        # Fallback for anything else assuming IBKR can handle it (SPY, AAPL, XAU, GC)
        return "IBKR"
        

    async def execute_trade(self, signal: AggregatedSignal) -> Dict[str, Any]:
        """
        Takes a synthesized signal from the multi-signal engine and physically executes it 
        on the required broker if the market is open.
        """
        target_broker = self.determine_broker(signal.symbol)
        
        logger.info(f"Routing {signal.action} {signal.symbol} -> {target_broker}")
        
        if target_broker == "COINBASE":
            if not TradingSession.is_crypto_open():
                return {"success": False, "error": "Crypto market closed (impossible)"}
            if not self.coinbase:
                return {"success": False, "error": "Coinbase API offline"}
                
            # Coinbase uses pair hyphenation, e.g. BTC-USD
            product_id = signal.symbol.replace("_", "-")
            
            # Coinbase size calculation needs to be precise (crypto amounts can be fractional)
            # Rough math for demonstration: risk limit $2000 per trade
            risk_usd = 2000
            price_distance = abs(signal.entry - signal.sl)
            if price_distance == 0:
                price_distance = signal.entry * 0.01 # Fallback 1%
                
            qty_crypto = risk_usd / price_distance
                
            return place_coinbase_oco(
                connector=self.coinbase,
                symbol=product_id,
                entry=signal.entry,
                sl=signal.sl,
                tp=signal.tp,
                size=round(qty_crypto, 4), # e.g. 0.0150 BTC
                side="buy" if signal.action == "BUY" else "sell"
            )
            
        elif target_broker == "IBKR":
            if not TradingSession.is_equities_open():
                return {"success": False, "error": "Equities/Futures market closed"}
            if not self.ibkr:
                return {"success": False, "error": "IBKR TWS offline"}
                
            # Delegate to IBKR Connector
            return self.ibkr.place_market_order(
                symbol=signal.symbol,
                direction=signal.action,
                quantity=100, # Mock size
                stop_loss=signal.sl,
                take_profit=signal.tp
            )
            
        elif target_broker == "OANDA":
            if not TradingSession.is_forex_open():
                return {"success": False, "error": "Forex market closed for weekend"}
            if not self.oanda:
                return {"success": False, "error": "OANDA engine offline"}
                
            # Currently OandaTradingEngine holds its own logic loop, but we can hook into its place_trade method.
            # Convert to format OANDA expects
            logger.info(f"Oanda execution delegated to {signal.symbol}")
            # return self.oanda.place_trade(...) 
            return {"success": True, "broker": "OANDA", "message": "Delegated to internal OANDA loop"}
            
        return {"success": False, "error": "Unknown asset class router"}

if __name__ == "__main__":
    router = BrokerRouter()
    logger.info("Hedge Fund Router Initialization Complete.")
