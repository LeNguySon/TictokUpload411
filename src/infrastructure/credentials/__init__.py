"""Credentials and Security Package."""

from src.infrastructure.credentials.dpapi import (
    SecretProtectionError,
    dpapi_protect,
    dpapi_unprotect,
    protect_text,
    unprotect_text,
)
from src.infrastructure.credentials.windows_vault import WindowsCredentialVault

__all__ = [
    "SecretProtectionError",
    "WindowsCredentialVault",
    "dpapi_protect",
    "dpapi_unprotect",
    "protect_text",
    "unprotect_text",
]
