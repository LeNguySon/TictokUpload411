"""
Passphrase encryption for backup bundles (Nhận và Gửi).

Bundles carry cookies and passwords and must move between machines, where DPAPI values cannot be decrypted,
so the manifest is encrypted with a key derived from a user passphrase:
``MAGIC | salt(16) | nonce(12) | AES-256-GCM(ciphertext + tag)``, key = scrypt(passphrase, salt, n=2**15).
A wrong passphrase or a modified file raises BackupPasswordError (GCM authentication).
"""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"TAVMENC1"
_SALT_LEN = 16
_NONCE_LEN = 12
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1


class BackupPasswordError(ValueError):
    """Wrong passphrase, or the encrypted bundle was modified/corrupted."""


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P).derive(passphrase.encode("utf-8"))


def encrypt_bundle(data: bytes, passphrase: str) -> bytes:
    if not passphrase:
        raise ValueError("Cần mật khẩu để mã hoá file sao lưu")
    salt, nonce = os.urandom(_SALT_LEN), os.urandom(_NONCE_LEN)
    return MAGIC + salt + nonce + AESGCM(_key(passphrase, salt)).encrypt(nonce, data, MAGIC)


def decrypt_bundle(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise BackupPasswordError("File sao lưu không phải định dạng mã hoá TAVM")
    head = len(MAGIC)
    salt = blob[head : head + _SALT_LEN]
    nonce = blob[head + _SALT_LEN : head + _SALT_LEN + _NONCE_LEN]
    ciphertext = blob[head + _SALT_LEN + _NONCE_LEN :]
    try:
        return AESGCM(_key(passphrase or "", salt)).decrypt(nonce, ciphertext, MAGIC)
    except InvalidTag as e:
        raise BackupPasswordError("Sai mật khẩu hoặc file sao lưu đã bị thay đổi") from e
