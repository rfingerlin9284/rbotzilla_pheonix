#!/usr/bin/env python3
"""
Positions Registry - Cross-Platform Position Tracking
Prevents duplicate positions across multiple trading platforms (OANDA, IBKR, Coinbase)
PIN: 841921 | Generated: 2025-11-20
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from pathlib import Path
import fcntl
import time


class PositionsRegistry:
    """
    Thread-safe and process-safe registry for tracking active positions
    across multiple trading platforms.
    
    Prevents the same symbol from being traded on multiple platforms simultaneously.
    """
    
    def __init__(self, registry_file: str = '/tmp/rick_positions_registry.json'):
        """
        Initialize the positions registry.
        
        Args:
            registry_file: Path to the JSON file storing active positions
        """
        self.registry_file = registry_file
        self.lock_file = f"{registry_file}.lock"
        
    def _acquire_lock(self, timeout: int = 5) -> Optional[int]:
        """
        Acquire exclusive lock on registry file.
        
        Args:
            timeout: Maximum seconds to wait for lock
            
        Returns:
            File descriptor if lock acquired, None if timeout
        """
        lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lock_fd
            except IOError:
                time.sleep(0.1)
        
        os.close(lock_fd)
        return None
    
    def _release_lock(self, lock_fd: int):
        """Release the lock and close file descriptor."""
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except Exception:
                pass
    
    def _load_registry(self) -> Dict:
        """
        Load registry from file, handling missing or corrupted files.
        
        Returns:
            Dictionary with registry data
        """
        if not os.path.exists(self.registry_file):
            return {
                'positions': {},
                'last_update': datetime.now(timezone.utc).isoformat(),
                'version': '1.0'
            }
        
        try:
            with open(self.registry_file, 'r') as f:
                data = json.load(f)
                # Ensure required fields exist
                if 'positions' not in data:
                    data['positions'] = {}
                return data
        except (json.JSONDecodeError, IOError) as e:
            # Corrupted or unreadable file - return empty registry
            print(f"Warning: Registry file corrupted, creating new: {e}")
            return {
                'positions': {},
                'last_update': datetime.now(timezone.utc).isoformat(),
                'version': '1.0',
                'error': str(e)
            }
    
    def _save_registry(self, data: Dict):
        """
        Save registry to file atomically.
        
        Args:
            data: Registry data to save
        """
        data['last_update'] = datetime.now(timezone.utc).isoformat()
        
        # Write to temp file first, then rename (atomic operation)
        temp_file = f"{self.registry_file}.tmp"
        try:
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_file, self.registry_file)
        except Exception as e:
            print(f"Error saving registry: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise
    
    def register_position(self, symbol: str, platform: str, order_id: str, 
                         direction: str, notional_usd: float) -> bool:
        """
        Register a new position, checking for conflicts.
        
        Args:
            symbol: Trading symbol (e.g., 'EUR_USD')
            platform: Platform name (e.g., 'oanda', 'ibkr', 'coinbase')
            order_id: Unique order identifier
            direction: 'BUY' or 'SELL'
            notional_usd: Position size in USD
            
        Returns:
            True if position registered successfully, False if symbol already taken
        """
        lock_fd = self._acquire_lock()
        if lock_fd is None:
            raise TimeoutError("Could not acquire registry lock")
        
        try:
            registry = self._load_registry()
            positions = registry['positions']
            
            # Check if symbol already has an active position
            if symbol in positions:
                existing = positions[symbol]
                # Allow same platform to update (e.g., modify order)
                if existing['platform'] != platform:
                    return False
            
            # Register the position
            positions[symbol] = {
                'platform': platform,
                'order_id': order_id,
                'direction': direction,
                'notional_usd': notional_usd,
                'registered_at': datetime.now(timezone.utc).isoformat()
            }
            
            self._save_registry(registry)
            return True
            
        finally:
            self._release_lock(lock_fd)
    
    def unregister_position(self, symbol: str, platform: str) -> bool:
        """
        Remove a position from the registry.
        
        Args:
            symbol: Trading symbol
            platform: Platform name
            
        Returns:
            True if position was removed, False if not found or wrong platform
        """
        lock_fd = self._acquire_lock()
        if lock_fd is None:
            raise TimeoutError("Could not acquire registry lock")
        
        try:
            registry = self._load_registry()
            positions = registry['positions']
            
            if symbol not in positions:
                return False
            
            # Verify it's the correct platform before removing
            if positions[symbol]['platform'] != platform:
                return False
            
            del positions[symbol]
            self._save_registry(registry)
            return True
            
        finally:
            self._release_lock(lock_fd)
    
    def is_symbol_available(self, symbol: str) -> bool:
        """
        Check if a symbol is available for trading.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if symbol is available, False if already in use
        """
        lock_fd = self._acquire_lock()
        if lock_fd is None:
            raise TimeoutError("Could not acquire registry lock")
        
        try:
            registry = self._load_registry()
            return symbol not in registry['positions']
        finally:
            self._release_lock(lock_fd)
    
    def get_active_positions(self, platform: Optional[str] = None) -> Dict[str, Dict]:
        """
        Get all active positions, optionally filtered by platform.
        
        Args:
            platform: Optional platform filter
            
        Returns:
            Dictionary of active positions
        """
        lock_fd = self._acquire_lock()
        if lock_fd is None:
            raise TimeoutError("Could not acquire registry lock")
        
        try:
            registry = self._load_registry()
            positions = registry['positions']
            
            if platform is None:
                return positions.copy()
            
            # Filter by platform
            return {
                symbol: pos for symbol, pos in positions.items()
                if pos['platform'] == platform
            }
        finally:
            self._release_lock(lock_fd)
    
    def cleanup_stale_positions(self, max_age_hours: int = 24) -> int:
        """
        Remove positions older than specified age.
        
        Args:
            max_age_hours: Maximum age in hours before considering position stale
            
        Returns:
            Number of positions cleaned up
        """
        lock_fd = self._acquire_lock()
        if lock_fd is None:
            raise TimeoutError("Could not acquire registry lock")
        
        try:
            registry = self._load_registry()
            positions = registry['positions']
            
            now = datetime.now(timezone.utc)
            stale_symbols = []
            
            for symbol, pos in positions.items():
                try:
                    registered_at = datetime.fromisoformat(pos['registered_at'])
                    age_hours = (now - registered_at).total_seconds() / 3600
                    
                    if age_hours > max_age_hours:
                        stale_symbols.append(symbol)
                except (ValueError, KeyError):
                    # Invalid timestamp or missing field - remove it
                    stale_symbols.append(symbol)
            
            # Remove stale positions
            for symbol in stale_symbols:
                del positions[symbol]
            
            if stale_symbols:
                self._save_registry(registry)
            
            return len(stale_symbols)
            
        finally:
            self._release_lock(lock_fd)


def main():
    """CLI interface for positions registry"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Positions Registry Manager')
    parser.add_argument('--list', action='store_true', help='List all active positions')
    parser.add_argument('--cleanup', action='store_true', help='Clean up stale positions')
    parser.add_argument('--check', type=str, help='Check if symbol is available')
    parser.add_argument('--platform', type=str, help='Filter by platform')
    
    args = parser.parse_args()
    
    registry = PositionsRegistry()
    
    if args.list:
        positions = registry.get_active_positions(platform=args.platform)
        print(json.dumps(positions, indent=2))
    elif args.cleanup:
        count = registry.cleanup_stale_positions()
        print(f"Cleaned up {count} stale positions")
    elif args.check:
        available = registry.is_symbol_available(args.check)
        status = "AVAILABLE" if available else "IN USE"
        print(f"{args.check}: {status}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
