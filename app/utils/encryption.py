from cryptography.fernet import Fernet
import os
import base64


def get_encryption_key():
    """Get or generate encryption key"""
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        # Generate a key for development
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    return key.encode() if isinstance(key, str) else key


_cipher = Fernet(get_encryption_key())


def encrypt_value(value: str) -> str | None:
    """Encrypt a string value"""
    if not value:
        return None
    return _cipher.encrypt(value.encode()).decode()


def decrypt_value(encrypted_value: str) -> str | None:
    """Decrypt an encrypted value"""
    if not encrypted_value:
        return None
    return _cipher.decrypt(encrypted_value.encode()).decode()