"""Sensitive data encrypted storage — transparent encryption/decryption based on machine fingerprint

Uses Fernet (AES-128-CBC + HMAC-SHA256), key derived from local machine fingerprint, no password input required.
Encrypted values are stored in INI file with ENC: prefix, other fields remain in plaintext.

Usage:
    from secure_store import encrypt_value, decrypt_value

    encrypted = encrypt_value("sk-xxx")       # → "ENC:gAAAAAB..."
    decrypted = decrypt_value(encrypted)      # → "sk-xxx"
    decrypted = decrypt_value("plain-text")   # → "plain-text" (plaintext passthrough)
"""

import os
import sys
import base64
import hashlib
import platform
import getpass

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

ENC_PREFIX = "ENC:"
_SALT_FILENAME = ".key_salt"
_SALT_SIZE = 32
_PBKDF2_ITERATIONS = 600_000


def _get_data_dir():
    """Get data directory (for storing salt file), prefers LOCALAPPDATA, falls back to project directory"""
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            return os.path.join(local_appdata, "PixelBallPet")
    return os.path.dirname(os.path.abspath(__file__))


def _get_machine_fingerprint():
    """Combine hostname + username + platform info as machine fingerprint"""
    parts = [
        platform.node() or "unknown-host",
        getpass.getuser() or "unknown-user",
        platform.system() or "unknown-os",
    ]
    return "|".join(parts)


def _derive_key(salt: bytes) -> bytes:
    """Derive Fernet key from machine fingerprint + salt"""
    fingerprint = _get_machine_fingerprint().encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    raw_key = kdf.derive(fingerprint)
    return base64.urlsafe_b64encode(raw_key)


def _load_or_create_salt() -> bytes:
    """Load existing salt, create new one if it does not exist"""
    salt_path = os.path.join(_get_data_dir(), _SALT_FILENAME)
    try:
        with open(salt_path, "rb") as f:
            salt = f.read()
            if len(salt) == _SALT_SIZE:
                return salt
    except (FileNotFoundError, OSError):
        pass

    # Create new salt
    salt = os.urandom(_SALT_SIZE)
    os.makedirs(os.path.dirname(salt_path), exist_ok=True)
    try:
        with open(salt_path, "wb") as f:
            f.write(salt)
        # Hide salt file on Windows
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(salt_path, 2)  # FILE_ATTRIBUTE_HIDDEN
    except OSError:
        pass
    return salt


def _get_fernet() -> Fernet | None:
    """Get Fernet instance, returns None on failure"""
    try:
        salt = _load_or_create_salt()
        key = _derive_key(salt)
        return Fernet(key)
    except Exception:
        return None


def encrypt_value(plaintext: str) -> str:
    """Encrypt string, returns ciphertext with ENC: prefix"""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext  # Keep plaintext when encryption is unavailable
    token = f.encrypt(plaintext.encode("utf-8"))
    return ENC_PREFIX + base64.urlsafe_b64encode(token).decode("ascii")


def decrypt_value(value: str) -> str:
    """Decrypt string. Returns as-is if no ENC: prefix; returns empty string on decryption failure"""
    if not value or not value.startswith(ENC_PREFIX):
        return value
    f = _get_fernet()
    if f is None:
        return ""
    try:
        token = base64.urlsafe_b64decode(value[len(ENC_PREFIX):])
        return f.decrypt(token).decode("utf-8")
    except Exception:
        return ""  # Fingerprint changed or data corrupted → silently return empty, needs reconfiguration
