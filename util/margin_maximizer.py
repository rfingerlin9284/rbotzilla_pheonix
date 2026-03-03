"""
MARGIN MAXIMIZER
Increase position sizes to use more margin (5-10% per symbol)
instead of conservative 1.5%
Sizes based on account balance and risk parameters
"""

from typing import Dict, Optional
from dataclasses import dataclass
import json
from pathlib import Path

@dataclass
class MarginConfig:
    """Margin usage configuration"""
    # Risk per trade (as % of account)
    risk_per_trade_min: float = 0.05  # 0.5% minimum
    risk_per_trade_target: float = 0.10  # 1.0% target
    risk_per_trade_max: float = 0.15  # 1.5% aggressive maximum
    
    # Position sizing
    max_position_size_percent: float = 0.15  # Max 15% of account per symbol
    min_position_size_usd: float = 1000.0  # Min $1000 notional per position
    
    # Account balance thresholds for sizing
    account_balance_breakpoints = {
        10000: {'risk': 0.05, 'max_pos': 0.10},      # <$10k: conservative
        25000: {'risk': 0.10, 'max_pos': 0.15},      # $25k: moderate
        50000: {'risk': 0.15, 'max_pos': 0.20},      # $50k: aggressive
        100000: {'risk': 0.20, 'max_pos': 0.25},     # $100k+: very aggressive
    }
    
    # Correlation limits (don't stack too much capital in correlated pairs)
    max_correlated_pair_exposure: float = 0.25  # Max 25% combined in EUR/GBP/CHF pairs
    max_usd_pairs_exposure: float = 0.30  # Max 30% in all USD crosses
    
    # Drawdown-based position reduction
    reduce_size_if_drawdown_above: float = 0.05  # If DD >5%, reduce position size
    size_reduction_amount: float = 0.50  # Reduce by 50%
    position_size_recovery_after_profit: float = 0.10  # Resume normal sizing after 1% profit

class MarginMaximizer:
    """
    Dynamically calculate position sizes to maximize margin use
    while respecting risk limits
    """
    
    def __init__(self, config: MarginConfig = None):
        self.config = config or MarginConfig()
        self.account_balance = 25000.0  # Default (updated externally)
        self.current_drawdown = 0.0
        self.total_open_notional = 0.0  # Track total exposure
        
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_pips: float,
        account_balance: Optional[float] = None,
        current_drawdown: Optional[float] = None,
        existing_positions: Optional[Dict] = None,
    ) -> float:
        """
        Calculate position size in units for a symbol.
        
        Args:
            symbol: Trading pair (e.g., 'EUR_USD')
            entry_price: Entry price
            stop_loss_pips: Stop loss distance in pips
            account_balance: Current account balance
            current_drawdown: Current drawdown % (0.0 - 1.0)
            existing_positions: Dict of existing positions by symbol
        
        Returns:
            Position size in units
        """
        if account_balance:
            self.account_balance = account_balance
        if current_drawdown is not None:
            self.current_drawdown = current_drawdown
        
        existing_positions = existing_positions or {}
        
        # Step 1: Determine risk amount based on account balance
        risk_amount = self._get_risk_amount()
        
        # Step 2: Reduce risk if in drawdown
        if self.current_drawdown > self.config.reduce_size_if_drawdown_above:
            risk_amount *= self.config.size_reduction_amount
        
        # Step 3: Calculate units based on risk
        # Risk = position_size * (stop_loss_pips / 10000)
        # position_size = risk / stop_loss_pips * 10000
        stop_loss_fraction = stop_loss_pips / 10000.0  # Convert pips to decimal
        position_notional = risk_amount / stop_loss_fraction
        position_units = position_notional / entry_price
        
        # Step 4: Apply position size limits
        max_notional = self._get_max_position_notional(symbol, existing_positions)
        position_notional = min(position_notional, max_notional)
        position_units = position_notional / entry_price
        
        # Step 5: Ensure minimum size
        min_notional = self.config.min_position_size_usd
        if position_notional < min_notional:
            position_units = 0  # Skip trade if below minimum
            return 0.0
        
        return position_units
    
    def get_allocation_for_symbol(
        self,
        symbol: str,
        account_balance: Optional[float] = None,
        existing_positions: Optional[Dict] = None,
    ) -> Dict:
        """
        Get aggressive allocation for a symbol
        (Shows how much capital we're allocating)
        """
        if account_balance:
            self.account_balance = account_balance
        
        existing_positions = existing_positions or {}
        
        # Get target allocation % for this symbol
        risk_amount = self._get_risk_amount()
        target_notional = risk_amount / 0.01  # Convert risk to notional
        target_percent = (target_notional / self.account_balance) * 100
        
        max_notional = self._get_max_position_notional(symbol, existing_positions)
        max_percent = (max_notional / self.account_balance) * 100
        
        return {
            'symbol': symbol,
            'account_balance': self.account_balance,
            'target_notional': target_notional,
            'target_percent': target_percent,
            'max_notional': max_notional,
            'max_percent': max_percent,
            'risk_per_trade': self._get_risk_amount(),
            'can_trade': target_notional <= max_notional,
        }
    
    def _get_risk_amount(self) -> float:
        """Get risk amount in USD based on account balance"""
        if self.account_balance < 10000:
            risk_pct = self.config.risk_per_trade_min
        elif self.account_balance < 25000:
            risk_pct = self.config.risk_per_trade_target
        elif self.account_balance < 50000:
            risk_pct = self.config.risk_per_trade_target
        else:
            risk_pct = self.config.risk_per_trade_max
        
        return self.account_balance * risk_pct
    
    def _get_max_position_notional(
        self,
        symbol: str,
        existing_positions: Dict,
    ) -> float:
        """
        Get maximum position size for symbol considering:
        - Account balance %
        - Correlation with other open positions
        """
        # Base limit: X% of account
        if self.account_balance < 10000:
            max_percent = 0.10  # 10%
        elif self.account_balance < 50000:
            max_percent = 0.15  # 15%
        else:
            max_percent = 0.20  # 20% for larger accounts
        
        max_notional = self.account_balance * max_percent
        
        # Reduce if too much capital already in correlated pairs
        corr_groups = {
            'EUR': ['EUR_USD', 'EUR_GBP', 'EUR_JPY', 'EUR_CAD'],
            'GBP': ['GBP_USD', 'EUR_GBP', 'GBP_JPY'],
            'USD': ['EUR_USD', 'GBP_USD', 'USD_JPY', 'USD_CAD', 'AUD_USD'],
            'JPY': ['USD_JPY', 'EUR_JPY', 'GBP_JPY', 'AUD_JPY'],
        }
        
        # Find which correlation group this symbol belongs to
        symbol_prefix = symbol.split('_')[0]
        if symbol_prefix in corr_groups:
            corr_symbols = corr_groups[symbol_prefix]
            current_corr_exposure = sum(
                pos.get('notional', 0)
                for s, pos in existing_positions.items()
                if s in corr_symbols
            )
            
            corr_limit = self.account_balance * self.config.max_correlated_pair_exposure
            if current_corr_exposure >= corr_limit:
                max_notional = 0  # Can't add more in this group
            elif current_corr_exposure + max_notional > corr_limit:
                max_notional = corr_limit - current_corr_exposure
        
        return max(max_notional, 0)
    
    def print_allocation_report(self, account_balance: float):
        """Print how margin is allocated across symbols"""
        print("\n" + "="*80)
        print("MARGIN ALLOCATION REPORT")
        print("="*80)
        
        self.account_balance = account_balance
        risk_amount = self._get_risk_amount()
        
        print(f"Account Balance: ${account_balance:,.2f}")
        print(f"Current Drawdown: {self.current_drawdown:.2f}%")
        print(f"Risk Per Trade: ${risk_amount:.2f} ({(risk_amount/account_balance)*100:.2f}%)")
        print(f"\nPosition Size Limits (by symbol):")
        print(f"  Max Position Size: {(self.config.max_position_size_percent*100):.1f}% of account")
        print(f"  Max Notional Per Symbol: ${account_balance * self.config.max_position_size_percent:,.2f}")
        print(f"  Min Position Size: ${self.config.min_position_size_usd:,.2f}")
        
        print(f"\nCorrelated Pair Limits:")
        print(f"  EUR/GBP/CHF pairs combined: {(self.config.max_correlated_pair_exposure*100):.1f}% of account")
        print(f"  All USD crosses combined: {(self.config.max_usd_pairs_exposure*100):.1f}% of account")
        
        print(f"\nDrawdown Triggers:")
        print(f"  Reduce sizing if DD > {(self.config.reduce_size_if_drawdown_above*100):.1f}%")
        print(f"  Reduction amount: {(self.config.size_reduction_amount*100):.0f}%")
        
        print("="*80 + "\n")


def create_margin_maximizer_config(account_balance: float) -> MarginConfig:
    """Create a dynamic margin config based on account size"""
    config = MarginConfig()
    
    if account_balance < 10000:
        config.risk_per_trade_target = 0.05
        config.max_position_size_percent = 0.10
    elif account_balance < 50000:
        config.risk_per_trade_target = 0.10
        config.max_position_size_percent = 0.15
    else:
        config.risk_per_trade_target = 0.15
        config.max_position_size_percent = 0.20
    
    return config
