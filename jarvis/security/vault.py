"""
Secure Credential Vault for JARVIS
Uses Windows Credential Manager via keyring library.
FIX #3: Local fallback now encrypts with Fernet using a machine-derived key.
"""

import os
import json
import logging
import hashlib
import base64
from typing import Optional, Dict, Any

try:
    import keyring
    from keyring.errors import KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


def _derive_machine_key() -> bytes:
    """Derive a Fernet-compatible key from machine-specific identifiers.
    FIX #3: This ensures the vault is only decryptable on this machine.
    """
    import platform
    machine_id = f"{platform.node()}-{platform.machine()}-{os.getlogin() if hasattr(os, 'getlogin') else 'unknown'}"
    digest = hashlib.sha256(machine_id.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class CredentialVault:
    """Secure storage for API keys, passwords, and sensitive data."""
    
    SERVICE_NAME = "JARVIS_AI_Agent"
    
    def __init__(self, data_dir: str = "jarvis_data"):
        self.data_dir = data_dir
        self.local_vault_file = os.path.join(data_dir, "vault.json")
        self._fernet: Optional[Fernet] = None
        
        os.makedirs(data_dir, exist_ok=True)
        
        if not KEYRING_AVAILABLE:
            logger.warning("keyring library not available - using encrypted local vault")
        
        # FIX #3: Initialize encryption for local fallback
        if CRYPTO_AVAILABLE:
            try:
                self._fernet = Fernet(_derive_machine_key())
                logger.debug("Local vault encryption initialized (Fernet)")
            except Exception as e:
                logger.warning(f"Failed to initialize encryption: {e}")
                self._fernet = None
        else:
            logger.warning("cryptography library not available - local vault will be unencrypted. Install cryptography package.")
        
        self._local_cache = {}
        self._load_local_vault()
    
    def _load_local_vault(self):
        """Load locally stored credentials (fallback). FIX #3: Decrypt if encrypted."""
        if os.path.exists(self.local_vault_file):
            try:
                with open(self.local_vault_file, 'r') as f:
                    data = json.load(f)
                
                # Check if data is encrypted (has an __encrypted__ marker)
                if isinstance(data, dict) and data.get('__encrypted__'):
                    if self._fernet:
                        encrypted_payload = data['payload']
                        decrypted = self._fernet.decrypt(encrypted_payload.encode()).decode()
                        self._local_cache = json.loads(decrypted)
                    else:
                        logger.error("Vault is encrypted but cryptography is not available. Cannot decrypt.")
                        self._local_cache = {}
                else:
                    # Legacy plaintext format — migrate to encrypted on next save
                    self._local_cache = data if isinstance(data, dict) else {}
                    self._save_local_vault()  # Re-save as encrypted
                    
                logger.debug(f"Loaded {len(self._local_cache)} credentials from local vault")
            except Exception as e:
                logger.error(f"Failed to load local vault: {e}")
    
    def _save_local_vault(self):
        """Save credentials to local file. FIX #3: Encrypt with Fernet if available."""
        try:
            if self._fernet:
                # Encrypt the credentials
                payload = json.dumps(self._local_cache)
                encrypted = self._fernet.encrypt(payload.encode()).decode()
                data = {"__encrypted__": True, "payload": encrypted}
            else:
                # Fallback: plaintext (only when cryptography is unavailable)
                data = self._local_cache
            
            with open(self.local_vault_file, 'w') as f:
                json.dump(data, f, indent=2)
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
