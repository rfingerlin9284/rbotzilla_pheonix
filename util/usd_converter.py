"""
USD Notional Converter for OANDA Pairs
Handles all pair types: XXX_USD, USD_XXX, and XXX_YYY crosses
PIN: 841921
"""

def get_usd_notional(units: float, instrument: str, entry_price: float, oanda_connector=None) -> float:
    """
    Calculate TRUE USD notional for any OANDA pair.
    
    Args:
        units: Position size (positive or negative)
        instrument: OANDA format (e.g., "EUR_AUD", "USD_JPY", "GBP_USD")
        entry_price: Trade entry price
        oanda_connector: Optional OandaConnector instance for live price fetching
        
    Returns:
        USD notional value, or None if conversion failed
    """
    base, quote = instrument.split("_")
    units_abs = abs(float(units))
    price = float(entry_price)
    
    # Case 1: Quote currency is USD (e.g., EUR_USD, GBP_USD)
    if quote == "USD":
        return units_abs * price
    
    # Case 2: Base currency is USD (e.g., USD_JPY, USD_CHF)
    if base == "USD":
        return units_abs  # 1 unit = $1 USD notional
    
    # Case 3: Cross pair (e.g., EUR_AUD, NZD_CHF)
    # Need to convert quote currency to USD
    notional_in_quote = units_abs * price
    
    # Try to get live rate if connector provided
    quote_to_usd_rate = None
    
    if oanda_connector:
        try:
            # Try direct quote_USD pair first (e.g., AUD_USD)
            quote_usd_pair = f"{quote}_USD"
            price_data = oanda_connector.get_current_price(quote_usd_pair)
            if price_data and 'mid' in price_data:
                quote_to_usd_rate = float(price_data['mid'])
        except:
            pass
        
        if not quote_to_usd_rate:
            try:
                # Try inverse USD_quote pair (e.g., USD_AUD)
                usd_quote_pair = f"USD_{quote}"
                price_data = oanda_connector.get_current_price(usd_quote_pair)
                if price_data and 'mid' in price_data:
                    quote_to_usd_rate = 1.0 / float(price_data['mid'])
            except:
                pass
    
    # Fallback: Use approximate rates if live fetch failed
    if not quote_to_usd_rate:
        FALLBACK_RATES = {
            'AUD': 0.65, 'NZD': 0.60, 'CAD': 0.72, 'CHF': 1.13,
            'JPY': 0.0067, 'GBP': 1.27, 'EUR': 1.08
        }
        quote_to_usd_rate = FALLBACK_RATES.get(quote)
        if not quote_to_usd_rate:
            return None
    
    return notional_in_quote * quote_to_usd_rate
