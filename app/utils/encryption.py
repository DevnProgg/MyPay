import hashlib
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_response(response: str, merchant_key: str) -> dict:
    """
    Encrypt API response using AES-256-GCM.

    Returns a transport-safe payload the merchant can decrypt.
    """

    key = str(merchant_key).encode()
    if len(key) < 32:
        key = key.ljust(32, b"\0")
    else:
        key = key[:32]

    aesgcm = AESGCM(key)

    # Generate random IV (12 bytes for GCM)
    iv = os.urandom(12)

    # Serialize payload
    plaintext = response.encode()

    # Encrypt
    ciphertext = aesgcm.encrypt(iv, plaintext, None)

    #Return transport-safe structure
    return {
        "data": base64.b64encode(ciphertext).decode(),
        "iv": base64.b64encode(iv).decode(),
        "alg": "AES-256-GCM"
    }

import secrets


def generate_merchant_api_key(prefix: str = "mch_live",length: int = 32) -> str:
    """
    Generate a cryptographically secure merchant API key.

    Args:
        prefix: Key namespace
        length: Number of random bytes (not characters)

    Returns:
        str: Secure API key
    """

    # Generate secure random bytes and encode URL-safe
    random_part = secrets.token_urlsafe(length)

    return f"{prefix}_{random_part}"

def hash_string(string : str | None) -> str | None:
    if isinstance(string, str):
        return hashlib.sha256(string.encode()).hexdigest()
    return None