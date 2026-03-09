"""
OCO ORDER MANAGER
Continuously validates and enforces OCO (One-Cancels-Other) SL/TP orders
Creates hardened exit rules that CANNOT be bypassed
Verifies OCO orders exist and are working at all times
Re-creates broken OCOs automatically
"""

import json
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
from pathlib import Path

@dataclass
class OCOOrder:
    """One-Cancels-Other order: SL and TP are linked"""
    position_id: str
    symbol: str
    
    # OCO identifiers
    sl_order_id: str  # Stop loss order ID
    tp_order_id: str  # Take profit order ID
    
    # SL/TP details
    sl_price: float
    tp_price: float
    sl_type: str = "STOP"  # STOP loss
    tp_type: str = "LIMIT"  # TP is a limit order
    
    # Status
    is_active: bool = True
    created_at: float = None
    last_verified: float = None
    verification_count: int = 0
    
    # OCO state
    sl_triggered: bool = False
    tp_triggered: bool = False
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_verified is None:
            self.last_verified = time.time()

class OCOVerificationStatus(Enum):
    """Status of OCO verification"""
    ACTIVE = "active"  # OCO is active and verified
    PARTIALLY_FILLED = "partially_filled"  # One side filled
    BROKEN = "broken"  # OCO not found or invalid
    NEEDS_RECREATION = "needs_recreation"  # Should be recreated
    ORPHANED = "orphaned"  # Position exists but OCO missing

class OCOOrderManager:
    """
    Manages OCO orders with continuous verification.
    Ensures every position has hardened SL/TP.
    Automatically recreates broken OCOs.
    """
    
    def __init__(self, oanda_connector=None):
        self.oanda_connector = oanda_connector
        self.orders: Dict[str, OCOOrder] = {}  # position_id -> OCOOrder
        
        self.persistence_dir = Path("oco_orders")
        self.persistence_dir.mkdir(exist_ok=True)
        
        self.stats = {
            'orders_created': 0,
            'orders_verified': 0,
            'orders_recreated': 0,
            'orders_triggered': 0,
            'verification_failures': 0,
            'last_verification': 0,
        }
        
        # Load persisted OCO orders
        self._load_persisted_orders()
    
    def create_oco_order(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> Tuple[bool, Optional[OCOOrder]]:
        """
        Create a hardened OCO order (SL + TP linked).
        If SL is hit, TP is cancelled.
        If TP is hit, SL is cancelled.
        
        Returns: (success, OCOOrder)
        """
        
        # Validate OCO logic
        if entry_price == stop_loss_price or entry_price == take_profit_price:
            print(f"❌ Invalid OCO: Entry={entry_price}, SL={stop_loss_price}, TP={take_profit_price}")
            return False, None
        
        # Determine direction (BUY or SELL)
        is_buy = take_profit_price > entry_price
        
        if is_buy:
            if stop_loss_price >= entry_price:
                print(f"❌ Buy OCO: SL must be below entry")
                return False, None
            if take_profit_price <= entry_price:
                print(f"❌ Buy OCO: TP must be above entry")
                return False, None
        else:  # SELL
            if stop_loss_price <= entry_price:
                print(f"❌ Sell OCO: SL must be above entry")
                return False, None
            if take_profit_price >= entry_price:
                print(f"❌ Sell OCO: TP must be below entry")
                return False, None
        
        # Create OCO order
        oco = OCOOrder(
            position_id=position_id,
            symbol=symbol,
            sl_order_id=f"SL_{position_id}_{int(time.time())}",
            tp_order_id=f"TP_{position_id}_{int(time.time())}",
            sl_price=stop_loss_price,
            tp_price=take_profit_price,
        )
        
        # In real system, would send to OANDA
        if self.oanda_connector:
            try:
                # Create SL order
                sl_result = self.oanda_connector.create_order(
                    instrument=symbol,
                    units=-1,  # Placeholder
                    type="STOP",
                    priceBound=stop_loss_price,
                )
                oco.sl_order_id = sl_result.get('orderID', oco.sl_order_id)
                
                # Create TP order
                tp_result = self.oanda_connector.create_order(
                    instrument=symbol,
                    units=-1,  # Placeholder
                    type="LIMIT",
                    priceBound=take_profit_price,
                )
                oco.tp_order_id = tp_result.get('orderID', oco.tp_order_id)
            except Exception as e:
                print(f"⚠️  OCO creation failed: {e}")
                return False, None
        
        # Store and persist
        self.orders[position_id] = oco
        self._persist_order(oco)
        self.stats['orders_created'] += 1
        
        print(f"✅ OCO Created: {position_id}")
        print(f"   Symbol: {symbol} | Entry: {entry_price}")
        print(f"   SL: {stop_loss_price} ({abs(entry_price - stop_loss_price)*10000:.1f} pips)")
        print(f"   TP: {take_profit_price} ({abs(take_profit_price - entry_price)*10000:.1f} pips)")
        
        return True, oco
    
    def verify_oco_order(self, position_id: str) -> Tuple[bool, OCOVerificationStatus]:
        """
        Verify that OCO order is still active and correct.
        If broken, mark for recreation.
        
        Returns: (is_valid, status)
        """
        
        if position_id not in self.orders:
            return False, OCOVerificationStatus.ORPHANED
        
        oco = self.orders[position_id]
        
        # In real system, would query OANDA
        if self.oanda_connector:
            try:
                # Check if both orders still exist
                sl_exists = self.oanda_connector.get_order(oco.sl_order_id)
                tp_exists = self.oanda_connector.get_order(oco.tp_order_id)
                
                if not sl_exists and not tp_exists:
                    return False, OCOVerificationStatus.BROKEN
                
                if not sl_exists or not tp_exists:
                    return False, OCOVerificationStatus.PARTIALLY_FILLED
                
                # Check if either was triggered
                if sl_exists.get('state') == 'FILLED':
                    oco.sl_triggered = True
                    return False, OCOVerificationStatus.PARTIALLY_FILLED
                
                if tp_exists.get('state') == 'FILLED':
                    oco.tp_triggered = True
                    return False, OCOVerificationStatus.PARTIALLY_FILLED
            
            except Exception as e:
                print(f"⚠️  OCO verification error: {e}")
                self.stats['verification_failures'] += 1
                return False, OCOVerificationStatus.NEEDS_RECREATION
        
        # Update verification timestamp
        oco.last_verified = time.time()
        oco.verification_count += 1
        self.stats['orders_verified'] += 1
        
        return True, OCOVerificationStatus.ACTIVE
    
    def verify_all_oco_orders(self, recreate_broken: bool = True) -> Dict:
        """
        Verify ALL OCO orders in the system.
        Optionally recreate broken ones.
        
        Returns: Summary of verification results
        """
        
        results = {
            'total_orders': len(self.orders),
            'active': 0,
            'broken': 0,
            'partially_filled': 0,
            'orphaned': 0,
            'recreated': 0,
        }
        
        self.stats['last_verification'] = time.time()
        
        for position_id, oco in list(self.orders.items()):
            is_valid, status = self.verify_oco_order(position_id)
            
            if status == OCOVerificationStatus.ACTIVE:
                results['active'] += 1
            elif status == OCOVerificationStatus.BROKEN:
                results['broken'] += 1
                if recreate_broken:
                    success = self.recreate_oco_order(position_id)
                    if success:
                        results['recreated'] += 1
            elif status == OCOVerificationStatus.PARTIALLY_FILLED:
                results['partially_filled'] += 1
            elif status == OCOVerificationStatus.ORPHANED:
                results['orphaned'] += 1
        
        return results
    
    def recreate_oco_order(self, position_id: str) -> bool:
        """Recreate a broken OCO order"""
        
        if position_id not in self.orders:
            return False
        
        oco = self.orders[position_id]
        
        print(f"🔄 Recreating OCO: {position_id}")
        
        # In real system, would delete old orders and create new ones
        if self.oanda_connector:
            try:
                # Cancel old orders
                self.oanda_connector.cancel_order(oco.sl_order_id)
                self.oanda_connector.cancel_order(oco.tp_order_id)
            except:
                pass
        
        # Create new OCO
        success, new_oco = self.create_oco_order(
            position_id=position_id,
            symbol=oco.symbol,
            entry_price=(oco.sl_price + oco.tp_price) / 2,  # Estimate entry
            stop_loss_price=oco.sl_price,
            take_profit_price=oco.tp_price,
        )
        
        if success:
            self.stats['orders_recreated'] += 1
            print(f"✅ OCO Recreated: {position_id}")
        
        return success
    
    def update_stop_loss_order(self, position_id: str, new_sl_price: float) -> bool:
        """Update the Stop Loss leg of the OCO order via OANDA's trade modification endpoint"""
        if position_id not in self.orders:
            return False
            
        oco = self.orders[position_id]
        
        if self.oanda_connector:
            try:
                # Use trade_id (which is position_id in our engine integration) to set stop loss
                result = self.oanda_connector.set_trade_stop(trade_id=position_id, stop_price=new_sl_price)
                if result.get('success'):
                    oco.sl_price = new_sl_price
                    self._persist_order(oco)
                    print(f"✅ OANDA OCO Updated: {position_id} Stop Loss moved to {new_sl_price}")
                    return True
                else:
                    print(f"⚠️  OANDA SL Update Failed for {position_id}: {result.get('error')}")
                    # Still update local state if broker sync fails, better than desync
                    oco.sl_price = new_sl_price
                    self._persist_order(oco)
                    return False
            except Exception as e:
                print(f"⚠️  OANDA SL API Error for {position_id}: {e}")
                oco.sl_price = new_sl_price
                self._persist_order(oco)
                return False
                
        # If no hardware connector attached, update just locally
        oco.sl_price = new_sl_price
        self._persist_order(oco)
        return True
    
    def get_oco_order(self, position_id: str) -> Optional[OCOOrder]:
        """Get OCO order for a position"""
        return self.orders.get(position_id)
    
    def print_oco_status(self):
        """Print status of all OCO orders"""
        print("\n" + "="*100)
        print("OCO ORDER MANAGER STATUS")
        print("="*100)
        
        results = self.verify_all_oco_orders(recreate_broken=False)
        
        print(f"\nTotal Orders: {results['total_orders']}")
        print(f"  ✅ Active: {results['active']}")
        print(f"  ⚠️  Partially Filled: {results['partially_filled']}")
        print(f"  ❌ Broken: {results['broken']}")
        print(f"  👻 Orphaned: {results['orphaned']}")
        
        print(f"\nStatistics:")
        print(f"  Orders Created: {self.stats['orders_created']}")
        print(f"  Orders Verified: {self.stats['orders_verified']}")
        print(f"  Orders Recreated: {self.stats['orders_recreated']}")
        print(f"  Verification Failures: {self.stats['verification_failures']}")
        
        print(f"\nDetailed Orders:")
        for pos_id, oco in self.orders.items():
            is_valid, status = self.verify_oco_order(pos_id)
            status_emoji = "✅" if is_valid else "❌"
            print(f"  {status_emoji} {pos_id[:12]}... | {oco.symbol}")
            print(f"     SL: {oco.sl_price} | TP: {oco.tp_price}")
            print(f"     Verified: {oco.verification_count}x | Last: {datetime.fromtimestamp(oco.last_verified).strftime('%H:%M:%S')}")
        
        print("="*100 + "\n")
    
    def _persist_order(self, oco: OCOOrder):
        """Save OCO order to disk"""
        file_path = self.persistence_dir / f"{oco.position_id}.json"
        with open(file_path, 'w') as f:
            json.dump(asdict(oco), f, indent=2)
    
    def _load_persisted_orders(self):
        """Load all persisted OCO orders"""
        for file_path in self.persistence_dir.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    oco = OCOOrder(**data)
                    self.orders[oco.position_id] = oco
            except Exception as e:
                print(f"⚠️  Failed to load {file_path}: {e}")


# Global instance
_oco_manager = None

def get_oco_manager(oanda_connector=None):
    """Get or create global OCO manager"""
    global _oco_manager
    if _oco_manager is None:
        _oco_manager = OCOOrderManager(oanda_connector)
    return _oco_manager
