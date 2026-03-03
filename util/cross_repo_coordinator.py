"""
CROSS-REPO COORDINATOR
Synchronizes position state across cloned repositories.
Uses master-slave replication pattern.
- Master repo (local): Primary authority on positions
- Slave repos (clones): Read positions from master, execute locally
"""

import json
import time
import threading
import shutil
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

class CrossRepoCoordinator:
    """
    Sync positions across multiple RBOTZILLA clones.
    Ensures all repos know about:
    - All open positions (auto + manual)
    - Portfolio state
    - Risk metrics
    - Margin usage
    """
    
    def __init__(
        self,
        master_repo_path: str,
        slave_repo_paths: List[str] = None,
    ):
        self.master_repo_path = Path(master_repo_path)
        self.slave_repo_paths = [Path(p) for p in (slave_repo_paths or [])]
        
        self.is_syncing = False
        self.sync_thread = None
        self.sync_interval = 10  # seconds
        
        self.stats = {
            'syncs_performed': 0,
            'positions_synced': 0,
            'last_sync': 0,
            'sync_errors': 0,
        }
        
    def start_sync_loop(self, interval: int = 10):
        """Start continuous sync in background"""
        if self.is_syncing:
            return
        
        self.is_syncing = True
        self.sync_interval = interval
        
        self.sync_thread = threading.Thread(
            target=self._sync_loop,
            daemon=True,
            name="CrossRepoCoordinator"
        )
        self.sync_thread.start()
        
        print(f"🔄 Cross-Repo Coordinator started (sync every {interval}s)")
    
    def stop_sync_loop(self):
        """Stop background sync"""
        self.is_syncing = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        print("⏹️  Cross-Repo Coordinator stopped")
    
    def _sync_loop(self):
        """Main sync loop"""
        while self.is_syncing:
            try:
                self.sync_all()
                time.sleep(self.sync_interval)
            except Exception as e:
                print(f"⚠️  Sync error: {e}")
                self.stats['sync_errors'] += 1
                time.sleep(self.sync_interval)
    
    def sync_all(self):
        """Sync all slave repos with master"""
        # Master reads its portfolio state
        master_portfolio = self._read_portfolio_from_repo(self.master_repo_path)
        
        if not master_portfolio:
            return
        
        # Broadcast to all slaves
        for slave_path in self.slave_repo_paths:
            self._sync_slave(slave_path, master_portfolio)
        
        self.stats['syncs_performed'] += 1
        self.stats['last_sync'] = time.time()
    
    def _read_portfolio_from_repo(self, repo_path: Path) -> Optional[Dict]:
        """Read all positions from a repo"""
        registry_dir = repo_path / "portfolio_registry"
        
        if not registry_dir.exists():
            return None
        
        positions = {}
        for pos_file in registry_dir.glob("*.json"):
            if pos_file.name.startswith("portfolio_snapshot"):
                continue  # Skip snapshots
            
            try:
                with open(pos_file) as f:
                    pos_data = json.load(f)
                    positions[pos_data['position_id']] = pos_data
            except:
                pass
        
        return {
            'repo_path': str(repo_path),
            'timestamp': time.time(),
            'positions': positions,
            'position_count': len(positions),
        }
    
    def _sync_slave(self, slave_path: Path, master_portfolio: Dict):
        """Push master portfolio to a slave repo"""
        slave_registry_dir = slave_path / "portfolio_registry"
        slave_registry_dir.mkdir(exist_ok=True, parents=True)
        
        # Copy all position files from master to slave
        master_registry_dir = self.master_repo_path / "portfolio_registry"
        
        if not master_registry_dir.exists():
            return
        
        synced = 0
        for master_pos_file in master_registry_dir.glob("*.json"):
            if master_pos_file.name.startswith("portfolio_snapshot"):
                continue
            
            try:
                slave_pos_file = slave_registry_dir / master_pos_file.name
                shutil.copy2(master_pos_file, slave_pos_file)
                synced += 1
            except Exception as e:
                print(f"⚠️  Failed to sync {master_pos_file.name}: {e}")
        
        # Create a sync metadata file
        sync_metadata = {
            'synced_at': time.time(),
            'synced_from': str(self.master_repo_path),
            'positions_synced': synced,
            'master_snapshot': master_portfolio,
        }
        
        sync_file = slave_registry_dir / f"sync_metadata_{int(time.time())}.json"
        with open(sync_file, 'w') as f:
            json.dump(sync_metadata, f, indent=2)
        
        self.stats['positions_synced'] += synced
    
    def broadcast_critical_update(self, update_type: str, data: Dict):
        """
        Immediately broadcast a critical update to all slaves
        (Don't wait for next sync interval)
        
        Examples:
        - New position opened
        - Position closed
        - Critical risk event
        """
        update_message = {
            'timestamp': time.time(),
            'type': update_type,
            'data': data,
            'from_repo': str(self.master_repo_path),
        }
        
        for slave_path in self.slave_repo_paths:
            try:
                alert_dir = slave_path / "coordination_alerts"
                alert_dir.mkdir(exist_ok=True, parents=True)
                
                alert_file = alert_dir / f"alert_{int(time.time()*1000)}.json"
                with open(alert_file, 'w') as f:
                    json.dump(update_message, f, indent=2)
            except Exception as e:
                print(f"⚠️  Failed to send alert to {slave_path}: {e}")
    
    def get_sync_status(self) -> Dict:
        """Get current sync status"""
        return {
            'is_syncing': self.is_syncing,
            'syncs_performed': self.stats['syncs_performed'],
            'positions_synced': self.stats['positions_synced'],
            'sync_errors': self.stats['sync_errors'],
            'last_sync': datetime.fromtimestamp(self.stats['last_sync']) if self.stats['last_sync'] else None,
            'slave_repos': len(self.slave_repo_paths),
        }
    
    def print_sync_report(self):
        """Print sync status report"""
        status = self.get_sync_status()
        
        print("\n" + "="*80)
        print("CROSS-REPO COORDINATOR REPORT")
        print("="*80)
        print(f"Status: {'🟢 SYNCING' if status['is_syncing'] else '🔴 STOPPED'}")
        print(f"Master: {self.master_repo_path}")
        print(f"Slave Repos: {status['slave_repos']}")
        print(f"\nStatistics:")
        print(f"  Syncs Performed: {status['syncs_performed']}")
        print(f"  Positions Synced: {status['positions_synced']}")
        print(f"  Sync Errors: {status['sync_errors']}")
        print(f"  Last Sync: {status['last_sync']}")
        print("="*80 + "\n")


def create_coordinator_for_clones(
    master_repo_path: str = "/home/rfing/RBOTZILLA_PHOENIX",
) -> CrossRepoCoordinator:
    """
    Create coordinator that syncs master repo to all local clones
    """
    master_path = Path(master_repo_path)
    
    # Find clones (look for rbtz_pheonix_1, rbtz_pheonix_2, etc in same parent)
    parent_dir = master_path.parent
    clone_paths = [
        str(p) for p in parent_dir.glob("rbtz_pheonix_*")
        if p.is_dir() and p != master_path
    ]
    
    print(f"Found {len(clone_paths)} clone repositories:")
    for cp in clone_paths:
        print(f"  - {cp}")
    
    coordinator = CrossRepoCoordinator(
        master_repo_path=master_repo_path,
        slave_repo_paths=clone_paths,
    )
    
    return coordinator
