"""Windows DPAPI data protection for sensitive fields (cookies, secrets, tokens).
Complies with AgentShield Tier-1 Security Standard.
Full interoperability with Gloglin DPAPI encryption envelope ('gloglin:dpapi:v1:').
"""

from __future__ import annotations

import base64
import binascii
import ctypes
import hashlib
import os
from ctypes import wintypes

TEXT_PREFIX = "gloglin:dpapi:v1:"


class SecretProtectionError(RuntimeError):
    """Raised when protected data cannot be safely encrypted or decrypted."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _native_transform(data: bytes, entropy: bytes | None, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise SecretProtectionError("Windows user data protection (DPAPI) is unavailable on this OS")
    if not isinstance(data, bytes) or (entropy is not None and not isinstance(entropy, bytes)):
        raise TypeError("DPAPI inputs must be bytes")
    if len(data) > 0xFFFFFFFF:
        raise SecretProtectionError("DPAPI input exceeds the supported size limit")

    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        blob_ptr = ctypes.POINTER(_DataBlob)
        crypt32.CryptProtectData.argtypes = [
            blob_ptr,
            wintypes.LPCWSTR,
            blob_ptr,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            blob_ptr,
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            blob_ptr,
            ctypes.c_void_p,
            blob_ptr,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            blob_ptr,
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        source_buffer = (ctypes.c_ubyte * max(1, len(data)))()
        ctypes.memmove(source_buffer, data, len(data))
        source = _DataBlob(len(data), source_buffer)

        entropy_buffer = (ctypes.c_ubyte * max(1, len(entropy or b"")))()
        if entropy:
            ctypes.memmove(entropy_buffer, entropy, len(entropy))
        entropy_blob = _DataBlob(len(entropy or b""), entropy_buffer)
        output = _DataBlob()

        try:
            operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
            succeeded = operation(
                ctypes.byref(source),
                None,
                ctypes.byref(entropy_blob) if entropy is not None else None,
                None,
                None,
                1,  # CRYPTPROTECT_UI_FORBIDDEN
                ctypes.byref(output),
            )
            if not succeeded:
                raise SecretProtectionError(
                    f"Windows DPAPI operation failed (system error code {ctypes.get_last_error()})"
                )
            return ctypes.string_at(output.data, output.size)
        finally:
            ctypes.memset(source_buffer, 0, len(source_buffer))
            ctypes.memset(entropy_buffer, 0, len(entropy_buffer))
            if output.data:
                ctypes.memset(output.data, 0, output.size)
                kernel32.LocalFree(output.data)
    except (OSError, AttributeError) as exc:
        raise SecretProtectionError("Windows data protection is unavailable") from exc


def dpapi_protect(data: bytes, entropy: bytes | None = None) -> bytes:
    """Native DPAPI format; entropy=None interoperates with Chromium Local State."""
    return _native_transform(data, entropy, decrypt=False)


def dpapi_unprotect(data: bytes, entropy: bytes | None = None) -> bytes:
    """Decrypts raw DPAPI ciphertext."""
    return _native_transform(data, entropy, decrypt=True)


def _purpose_entropy(purpose: str) -> bytes:
    if not isinstance(purpose, str) or not purpose:
        raise ValueError("Secret purpose is required")
    return hashlib.sha256(b"Gloglin protected data\x00" + purpose.encode("utf-8")).digest()


def protect_bytes(data: bytes, purpose: str) -> bytes:
    return dpapi_protect(data, _purpose_entropy(purpose))


def unprotect_bytes(data: bytes, purpose: str) -> bytes:
    return dpapi_unprotect(data, _purpose_entropy(purpose))


def protect_text(value: str | None, purpose: str = "database-secrets-v1") -> str | None:
    """Protects plaintext into base64 ciphertext with TEXT_PREFIX envelope."""
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        raise TypeError("Protected database values must be text")
    if value.startswith(TEXT_PREFIX):
        unprotect_text(value, purpose)
        return value
    encoded = value.encode("utf-8")
    payload = protect_bytes(encoded, purpose)
    if unprotect_bytes(payload, purpose) != encoded:
        raise SecretProtectionError("Protected text failed read-back verification")
    return TEXT_PREFIX + base64.b64encode(payload).decode("ascii")


def unprotect_text(value: str | None, purpose: str = "database-secrets-v1") -> str | None:
    """Unprotects envelope ciphertext back to plaintext; returns raw text if not encrypted."""
    if value is None or value == "" or not isinstance(value, str) or not value.startswith(TEXT_PREFIX):
        return value
    try:
        payload = base64.b64decode(value[len(TEXT_PREFIX) :], validate=True)
        return unprotect_bytes(payload, purpose).decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise SecretProtectionError("Protected text is malformed or corrupted") from exc
