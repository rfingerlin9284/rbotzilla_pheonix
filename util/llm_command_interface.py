"""
LLM COMMAND INTERFACE
Allows manual position opening via LLM prompts/commands
All manually-created positions register in the universal registry
Integrated with aggressive portfolio monitor for unified tracking
"""

import json
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from pathlib import Path

from util.universal_position_registry import (
    get_registry,
    PositionSource,
    SLMode,
)

class TradeCommand(Enum):
    """LLM command types"""
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"
    MODIFY_SL = "modify_sl"
    MODIFY_TP = "modify_tp"
    SET_MANUAL_OVERRIDE = "manual_override"

@dataclass
class LLMTradeCommand:
    """Parsed LLM trade command"""
    command: TradeCommand
    symbol: str
    entry_price: float
    size_units: float
    stop_loss: float
    take_profit: float
    strategy_name: str = "LLM_Manual"
    confidence: float = 0.5  # User confidence in trade
    time_limit_minutes: Optional[int] = None  # Close after X minutes if no profit
    reasoning: str = ""  # Why user opened this trade

class LLMCommandInterface:
    """
    Handle manual trading commands from LLM agent.
    All trades register in universal registry.
    """
    
    def __init__(self):
        self.registry = get_registry()
        self.command_history: List[Dict] = []
        self.command_log_file = Path("logs/llm_commands.jsonl")
        self.command_log_file.parent.mkdir(exist_ok=True)
    
    def parse_command(self, command_text: str) -> Optional[LLMTradeCommand]:
        """
        Parse natural language command into structured trade.
        Examples:
        - "Buy EUR_USD at 1.0950, SL 1.0940, TP 1.0975"
        - "Sell GBP_USD 0.5 lots at 1.2500, SL 1.2530, TP 1.2450"
        - "Close EUR_USD position #abc123"
        """
        # This would be more sophisticated in practice
        # For now, a simple parser
        
        import re
        
        # Pattern: BUY/SELL SYMBOL @ PRICE SL TP
        pattern = r'(buy|sell)\s+(\w+_\w+)\s+(?:at|@)?\s*(\d+\.\d+)\s+sl\s*(\d+\.\d+)\s+tp\s*(\d+\.\d+)'
        match = re.search(pattern, command_text.lower())
        
        if match:
            command_type = TradeCommand.BUY if match.group(1) == 'buy' else TradeCommand.SELL
            return LLMTradeCommand(
                command=command_type,
                symbol=match.group(2).upper(),
                entry_price=float(match.group(3)),
                size_units=1.0,  # Default 1 lot
                stop_loss=float(match.group(4)),
                take_profit=float(match.group(5)),
                reasoning=command_text,
            )
        
        return None
    
    def execute_buy_command(
        self,
        symbol: str,
        entry_price: float,
        size_units: float,
        stop_loss: float,
        take_profit: float,
        **metadata
    ) -> str:
        """
        Execute a BUY trade command.
        Registers in universal position registry.
        Returns: position_id
        """
        # Validate inputs
        if size_units <= 0:
            print(f"❌ Invalid size: {size_units}")
            return ""
        
        if stop_loss >= entry_price:
            print(f"❌ SL must be below entry for BUY")
            return ""
        
        if take_profit <= entry_price:
            print(f"❌ TP must be above entry for BUY")
            return ""
        
        # Register in universal registry
        position_id = self.registry.open_position(
            symbol=symbol,
            entry_price=entry_price,
            size_units=size_units,
            initial_sl=stop_loss,
            take_profit=take_profit,
            source=PositionSource.MANUAL_PROMPT,
            entry_strategy=metadata.get('strategy_name', 'LLM_Manual_Buy'),
            entry_signal_confidence=metadata.get('confidence', 50),
            is_auto_managed=False,  # User manages until they set otherwise
        )
        
        # Log the command
        self._log_command({
            'timestamp': time.time(),
            'type': 'BUY',
            'symbol': symbol,
            'position_id': position_id,
            'entry_price': entry_price,
            'size_units': size_units,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'metadata': metadata,
            'status': 'EXECUTED',
        })
        
        print(f"✅ Buy Command Executed: {position_id}")
        print(f"   {symbol} {size_units} lots @ {entry_price}")
        print(f"   SL: {stop_loss} | TP: {take_profit}")
        
        return position_id
    
    def execute_sell_command(
        self,
        symbol: str,
        entry_price: float,
        size_units: float,
        stop_loss: float,
        take_profit: float,
        **metadata
    ) -> str:
        """
        Execute a SELL trade command.
        Registers in universal position registry.
        Returns: position_id
        """
        # Validate inputs
        if size_units <= 0:
            print(f"❌ Invalid size: {size_units}")
            return ""
        
        if stop_loss <= entry_price:
            print(f"❌ SL must be above entry for SELL")
            return ""
        
        if take_profit >= entry_price:
            print(f"❌ TP must be below entry for SELL")
            return ""
        
        # Register in universal registry
        position_id = self.registry.open_position(
            symbol=symbol,
            entry_price=entry_price,
            size_units=size_units,
            initial_sl=stop_loss,
            take_profit=take_profit,
            source=PositionSource.MANUAL_PROMPT,
            entry_strategy=metadata.get('strategy_name', 'LLM_Manual_Sell'),
            entry_signal_confidence=metadata.get('confidence', 50),
            is_auto_managed=False,  # User manages until they set otherwise
        )
        
        # Log the command
        self._log_command({
            'timestamp': time.time(),
            'type': 'SELL',
            'symbol': symbol,
            'position_id': position_id,
            'entry_price': entry_price,
            'size_units': size_units,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'metadata': metadata,
            'status': 'EXECUTED',
        })
        
        print(f"✅ Sell Command Executed: {position_id}")
        print(f"   {symbol} {size_units} lots @ {entry_price}")
        print(f"   SL: {stop_loss} | TP: {take_profit}")
        
        return position_id
    
    def execute_close_command(self, position_id: str, reason: str = "User manual close") -> bool:
        """Close a manually-opened position"""
        position = self.registry.get_position_by_id(position_id)
        
        if not position:
            print(f"❌ Position not found: {position_id}")
            return False
        
        # Close at current price (in real system, would fetch actual market price)
        close_price = position.metrics.current_price or position.entry_price
        
        success = self.registry.close_position(
            position_id,
            close_price,
            reason
        )
        
        if success:
            self._log_command({
                'timestamp': time.time(),
                'type': 'CLOSE',
                'position_id': position_id,
                'symbol': position.symbol,
                'close_price': close_price,
                'reason': reason,
                'status': 'EXECUTED',
            })
        
        return success
    
    def execute_modify_sl_command(self, position_id: str, new_sl: float) -> bool:
        """User manually modifies stop loss"""
        position = self.registry.get_position_by_id(position_id)
        
        if not position:
            print(f"❌ Position not found: {position_id}")
            return False
        
        success = self.registry.move_stop_loss(
            position_id,
            new_sl,
            SLMode.MANUAL_OVERRIDE,
            f"User manual SL adjustment from {position.current_sl} to {new_sl}"
        )
        
        if success:
            # Set manual override to lock it
            self.registry.set_manual_override(position_id, 3600)  # 1 hour override
            
            self._log_command({
                'timestamp': time.time(),
                'type': 'MODIFY_SL',
                'position_id': position_id,
                'old_sl': position.current_sl,
                'new_sl': new_sl,
                'status': 'EXECUTED',
            })
        
        return success
    
    def enable_auto_management(self, position_id: str) -> bool:
        """
        User wants to hand over position to auto-management.
        System can now adjust SL as needed.
        """
        position = self.registry.get_position_by_id(position_id)
        
        if not position:
            return False
        
        position.is_auto_managed = True
        position.manual_override_until = 0  # Clear override
        
        self._log_command({
            'timestamp': time.time(),
            'type': 'AUTO_MANAGEMENT_ENABLED',
            'position_id': position_id,
            'symbol': position.symbol,
            'status': 'EXECUTED',
        })
        
        print(f"✅ Auto-management enabled for {position_id}")
        return True
    
    def get_manual_positions(self) -> List[Dict]:
        """Get all manually-created positions (not autonomous)"""
        manual_positions = self.registry.get_positions_by_source(PositionSource.MANUAL_PROMPT)
        
        result = []
        for pos in manual_positions:
            result.append({
                'position_id': pos.position_id,
                'symbol': pos.symbol,
                'entry_price': pos.entry_price,
                'current_price': pos.metrics.current_price,
                'pnl_usd': pos.metrics.pnl_usd,
                'pnl_percent': pos.metrics.pnl_percent,
                'stop_loss': pos.current_sl,
                'take_profit': pos.take_profit,
                'is_auto_managed': pos.is_auto_managed,
                'age_seconds': int(time.time() - pos.entry_time),
            })
        
        return result
    
    def print_manual_positions_summary(self):
        """Print summary of all manually-opened positions"""
        positions = self.get_manual_positions()
        
        if not positions:
            print("No manual positions currently open")
            return
        
        print("\n" + "="*100)
        print("MANUAL POSITIONS (Opened via LLM Command)")
        print("="*100)
        
        total_pnl = 0
        for idx, pos in enumerate(positions, 1):
            color = "🟢" if pos['pnl_usd'] > 0 else "🔴"
            auto_label = "🤖 AUTO" if pos['is_auto_managed'] else "👤 MANUAL"
            
            print(f"\n{idx}. {color} {pos['symbol']} | {auto_label}")
            print(f"   Position ID: {pos['position_id']}")
            print(f"   Entry: {pos['entry_price']:.5f} → Current: {pos['current_price']:.5f}")
            print(f"   P&L: ${pos['pnl_usd']:+.2f} ({pos['pnl_percent']:+.2f}%)")
            print(f"   SL: {pos['stop_loss']:.5f} | TP: {pos['take_profit']:.5f}")
            print(f"   Age: {pos['age_seconds']} seconds")
            
            total_pnl += pos['pnl_usd']
        
        print(f"\n{'='*100}")
        print(f"Total Manual Positions: {len(positions)}")
        print(f"Total P&L: ${total_pnl:+.2f}")
        print(f"{'='*100}\n")
    
    def _log_command(self, command_data: Dict):
        """Log command to JSONL for audit"""
        with open(self.command_log_file, 'a') as f:
            f.write(json.dumps(command_data) + '\n')
        
        self.command_history.append(command_data)


# Global instance
_llm_interface = None

def get_llm_interface() -> LLMCommandInterface:
    """Get or create LLM command interface"""
    global _llm_interface
    if _llm_interface is None:
        _llm_interface = LLMCommandInterface()
    return _llm_interface
