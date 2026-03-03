import json
import os
import time
import logging
from typing import Any, Dict, Optional

class ParameterManager:
    """Centralized parameter management with locking and audit trail"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.locked_params = set()
        self.params = {}
        self.load_config()
        
        # Setup logging
        self.logger = logging.getLogger("parameter_manager")
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler("logs/parameter_changes.log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.params = json.load(f)
                    
                # Also load locked parameters if they exist
                lock_path = f"{self.config_path}.locks"
                if os.path.exists(lock_path):
                    with open(lock_path, 'r') as f:
                        self.locked_params = set(json.load(f))
            except Exception as e:
                self.logger.error(f"Error loading configuration: {str(e)}")
                self.params = {}
        else:
            self.params = {}
            self.save_config()
    
    def save_config(self):
        """Save configuration to file with backup"""
        try:
            # Create backup of current config
            if os.path.exists(self.config_path):
                backup_dir = os.path.join(os.path.dirname(self.config_path), "backups")
                os.makedirs(backup_dir, exist_ok=True)
                backup_path = os.path.join(backup_dir, f"{os.path.basename(self.config_path)}.{int(time.time())}.bak")
                with open(self.config_path, 'r') as src, open(backup_path, 'w') as dst:
                    dst.write(src.read())
            
            # Write new config
            with open(self.config_path, 'w') as f:
                json.dump(self.params, f, indent=2)
                
            # Save locked parameters
            lock_path = f"{self.config_path}.locks"
            with open(lock_path, 'w') as f:
                json.dump(list(self.locked_params), f)
                
            return True
        except Exception as e:
            self.logger.error(f"Error saving configuration: {str(e)}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get parameter value"""
        return self.params.get(key, default)
    
    def set(self, key: str, value: Any, component: str) -> bool:
        """Set parameter value with audit logging"""
        if key in self.locked_params:
            self.logger.warning(f"Attempted to modify locked parameter '{key}' by {component}")
            return False
        
        old_value = self.params.get(key)
        self.params[key] = value
        success = self.save_config()
        
        if success:
            # Log the change
            self.logger.info(f"Parameter '{key}' changed by {component}: {old_value} -> {value}")
            return True
        return False
    
    def lock_parameter(self, key: str):
        """Lock a parameter to prevent changes"""
        if key in self.params:
            self.locked_params.add(key)
            self.logger.info(f"Parameter '{key}' locked with value: {self.params[key]}")
            self.save_config()
    
    def unlock_parameter(self, key: str):
        """Unlock a parameter to allow changes"""
        if key in self.locked_params:
            self.locked_params.remove(key)
            self.logger.info(f"Parameter '{key}' unlocked")
            self.save_config()
            
    def get_all_parameters(self):
        """Get all parameters as a dictionary"""
        return self.params.copy()
    
    def get_locked_parameters(self):
        """Get all locked parameters as a set"""
        return self.locked_params.copy()
    
    def bulk_update(self, params_dict: Dict[str, Any], component: str) -> bool:
        """Update multiple parameters at once"""
        # First check if any parameters are locked
        for key in params_dict:
            if key in self.locked_params:
                self.logger.warning(f"Bulk update contains locked parameter '{key}' from {component}")
                return False
        
        # If all clear, update all parameters
        for key, value in params_dict.items():
            old_value = self.params.get(key)
            self.params[key] = value
            self.logger.info(f"Parameter '{key}' changed by {component}: {old_value} -> {value}")
        
        return self.save_config()

# Singleton instance
_instance = None

def get_parameter_manager(config_path=None):
    """Get the singleton instance of ParameterManager"""
    global _instance
    if _instance is None:
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "system_parameters.json")
        _instance = ParameterManager(config_path)
    return _instance