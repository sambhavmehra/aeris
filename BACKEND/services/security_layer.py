"""
AERIS - Security Layer
PIN authentication, encrypted API key storage, system locking.
"""
import logging
import os
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class SecurityLayer:
    """Security: PIN auth, encrypted key storage"""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.master_key_path = self.data_dir / ".master.key"
        self.pin_path = self.data_dir / ".pin.hash"
        self.locked = False
        self._fernet = None
        self._init_encryption()

    def _init_encryption(self):
        try:
            from cryptography.fernet import Fernet
            if self.master_key_path.exists():
                key = self.master_key_path.read_bytes()
            else:
                key = Fernet.generate_key()
                self.master_key_path.write_bytes(key)
            self._fernet = Fernet(key)
        except Exception as e:
            logger.warning(f"Encryption init failed: {e}")

    def set_pin(self, pin):
        """Set a new PIN"""
        try:
            import bcrypt
            hashed = bcrypt.hashpw(pin.encode(), bcrypt.gensalt())
            self.pin_path.write_bytes(hashed)
            return True
        except Exception as e:
            logger.error(f"PIN set error: {e}")
            return False

    def verify_pin(self, pin):
        """Verify PIN"""
        try:
            import bcrypt
            if not self.pin_path.exists():
                return True  # No PIN set
            stored = self.pin_path.read_bytes()
            return bcrypt.checkpw(pin.encode(), stored)
        except Exception as e:
            logger.error(f"PIN verify error: {e}")
            return False

    def lock(self):
        self.locked = True
        return True

    def unlock(self, pin):
        if self.verify_pin(pin):
            self.locked = False
            return True
        return False

    def is_locked(self):
        return self.locked

    def encrypt_value(self, value):
        """Encrypt a string value"""
        if not self._fernet:
            return None
        try:
            return self._fernet.encrypt(value.encode()).decode()
        except Exception:
            return None

    def decrypt_value(self, token):
        """Decrypt an encrypted value"""
        if not self._fernet:
            return None
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except Exception:
            return None

    def store_key(self, name, value):
        """Store an encrypted API key"""
        keys_path = self.data_dir / ".keys.enc"
        keys = {}
        if keys_path.exists():
            try:
                data = self.decrypt_value(keys_path.read_text())
                if data:
                    keys = json.loads(data)
            except Exception:
                pass
        keys[name] = value
        encrypted = self.encrypt_value(json.dumps(keys))
        if encrypted:
            keys_path.write_text(encrypted)
            return True
        return False

    def get_key(self, name):
        """Retrieve an encrypted API key"""
        keys_path = self.data_dir / ".keys.enc"
        if not keys_path.exists():
            return None
        try:
            data = self.decrypt_value(keys_path.read_text())
            if data:
                keys = json.loads(data)
                return keys.get(name)
        except Exception:
            return None
