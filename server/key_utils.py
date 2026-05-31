"""API Key generation and verification utilities."""
import secrets
import bcrypt as _bcrypt
import string

KEY_PREFIX = "minta_"
PREFIX_LENGTH = 8
SUFFIX_LENGTH = 32


def generate_api_key():
    """
    Generate a new API key.

    Returns:
        (full_key, prefix, hash)
        - full_key: the complete key to show to the user once (e.g. minta_a8f3kD9sL2pQ7wXe...)
        - prefix: first 8 chars after prefix for db lookup (e.g. a8f3kD9s)
        - hash: bcrypt hash of the full key
    """
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(PREFIX_LENGTH + SUFFIX_LENGTH))
    prefix = random_part[:PREFIX_LENGTH]
    suffix = random_part[PREFIX_LENGTH:]
    full_key = f"{KEY_PREFIX}{prefix}{suffix}"
    key_hash = _bcrypt.hashpw(full_key.encode(), _bcrypt.gensalt()).decode()
    return full_key, prefix, key_hash


def verify_api_key(full_key: str, key_hash: str) -> bool:
    """Verify an API key against its bcrypt hash."""
    return _bcrypt.checkpw(full_key.encode(), key_hash.encode())
