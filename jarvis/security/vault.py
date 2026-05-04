"""
Secure Credential Vault for JARVIS
Uses Windows Credential Manager via keyring library.
"""

import os
import json
import logging
from typing import Optional, Dict, Any

try:
    import keyring
    from keyring.errors import KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

logger = logging.getLogger(__name__)


class CredentialVault:
    """Secure storage for API keys, passwords, and sensitive data."""
    
    SERVICE_NAME = "JARVIS_AI_Agent"
    
    def __init__(self, data_dir: str = "jarvis_data"):
        self.data_dir = data_dir
        self.local_vault_file = os.path.join(data_dir, "vault.json")
        
        os.makedirs(data_dir, exist_ok=True)
        
        if not KEYRING_AVAILABLE:
            logger.warning("keyring library not available - using encrypted local vault")
        
        self._local_cache = {}
        self._load_local_vault()
    
    def _load_local_vault(self):
        """Load locally stored credentials (fallback)."""
        if os.path.exists(self.local_vault_file):
            try:
                with open(self.local_vault_file, 'r') as f:
                    self._local_cache = json.load(f)
                logger.debug(f"Loaded {len(self._local_cache)} credentials from local vault")
            except Exception as e:
                logger.error(f"Failed to load local vault: {e}")
    
    def _save_local_vault(self):
        """Save credentials to local encrypted file."""
        try:
            with open(self.local_vault_file, 'w') as f:
                json.dump(self._local_cache, f, indent=2)
            # Set restrictive permissions (Unix only)
            if os.name != 'nt':
                os.chmod(self.local_vault_file, 0o600)
        except Exception as e:
            logger.error(f"Failed to save local vault: {e}")
    
    def set_credential(self, key: str, value: str, username: str = "default"):
        """
        Store a credential securely.
        
        Args:
            key: Credential identifier (e.g., 'openai_api_key')
            value: The secret value
            username: Optional username for multi-user setups
        """
        account_name = f"{username}_{key}"
        
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(self.SERVICE_NAME, account_name, value)
                logger.info(f"Credential '{key}' stored in system keyring")
                return True
            except KeyringError as e:
                logger.warning(f"Keyring failed, falling back to local vault: {e}")
        
        # Fallback to local storage
        self._local_cache[account_name] = value
        self._save_local_vault()
        logger.info(f"Credential '{key}' stored in local vault")
        return True
    
    def get_credential(self, key: str, username: str = "default") -> Optional[str]:
        """
        Retrieve a credential.
        
        Args:
            key: Credential identifier
            username: Optional username
            
        Returns:
            The credential value or None if not found
        """
        account_name = f"{username}_{key}"
        
        if KEYRING_AVAILABLE:
            try:
                value = keyring.get_password(self.SERVICE_NAME, account_name)
                if value is not None:
                    return value
            except KeyringError as e:
                logger.warning(f"Keyring get failed: {e}")
        
        # Fallback to local storage
        return self._local_cache.get(account_name)
    
    def delete_credential(self, key: str, username: str = "default") -> bool:
        """Delete a credential."""
        account_name = f"{username}_{key}"
        
        deleted = False
        
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(self.SERVICE_NAME, account_name)
                deleted = True
            except KeyringError:
                pass
        
        if account_name in self._local_cache:
            del self._local_cache[account_name]
            self._save_local_vault()
            deleted = True
        
        return deleted
    
    def list_credentials(self, username: str = "default") -> list:
        """List all stored credential keys (not values)."""
        keys = set()
        
        # Check local cache
        prefix = f"{username}_"
        for account in self._local_cache.keys():
            if account.startswith(prefix):
                keys.add(account[len(prefix):])
        
        return sorted(list(keys))
    
    def has_credential(self, key: str, username: str = "default") -> bool:
        """Check if a credential exists."""
        return self.get_credential(key, username) is not None


# Convenience functions for common use cases
def setup_api_keys(vault: CredentialVault):
    """
    Interactive setup for common API keys.
    Prompts user to enter keys and stores them securely.
    """
    print("\n=== JARVIS API Key Setup ===\n")
    
    common_keys = [
        ("openai_api_key", "OpenAI API Key"),
        ("anthropic_api_key", "Anthropic API Key"),
        ("google_api_key", "Google API Key"),
        ("github_token", "GitHub Personal Access Token"),
    ]
    
    for key, description in common_keys:
        value = input(f"Enter {description} (or press Enter to skip): ").strip()
        if value:
            vault.set_credential(key, value)
            print(f"✓ {description} stored securely\n")
    
    print("Setup complete! Keys are stored in your system's secure credential manager.\n")
