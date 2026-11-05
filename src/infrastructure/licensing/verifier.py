"""License key format: ``TAVM1.<base64url(payload_json)>.<base64url(ed25519_signature)>``.

The signature covers ``TAVM1.<payload>``. The app only holds public keys (``trusted_keys``); the private
signing key lives with the issuer tool, outside the app and the repository.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Collection, Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from src.domain.licensing.claims import InvalidClaimsError, LicenseClaims, LicenseStatus

KEY_PREFIX = "TAVM1"


class LicenseError(Exception):
    def __init__(self, status: LicenseStatus, detail: str = "") -> None:
        super().__init__(detail or status.value)
        self.status = status


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def encode_license(claims: Mapping[str, Any], private_key: Ed25519PrivateKey, kid: str) -> str:
    body = json.dumps({**claims, "kid": kid}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    signed = f"{KEY_PREFIX}.{_b64e(body.encode('utf-8'))}"
    return f"{signed}.{_b64e(private_key.sign(signed.encode('ascii')))}"


def normalize_key(key: str) -> str:
    """Users paste keys wrapped across lines / with spaces."""
    return "".join((key or "").split())


def decode_and_verify(key: str, trusted: Mapping[str, str], revoked: Collection[str] = ()) -> LicenseClaims:
    """Verifies the signature against the trusted public keys and returns the claims.

    Machine binding and expiry are checked by the license service (they depend on the machine and clock).
    """
    parts = normalize_key(key).split(".")
    if len(parts) != 3 or parts[0] != KEY_PREFIX or not parts[1] or not parts[2]:
        raise LicenseError(LicenseStatus.MALFORMED)
    try:
        signature = _b64d(parts[2])
        data = json.loads(_b64d(parts[1]).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeError) as exc:
        raise LicenseError(LicenseStatus.MALFORMED) from exc
    if not isinstance(data, dict):
        raise LicenseError(LicenseStatus.MALFORMED)

    kid = str(data.get("kid", ""))
    public_b64 = trusted.get(kid)
    if not public_b64:
        raise LicenseError(LicenseStatus.INVALID_SIGNATURE, "unknown signing key")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64)).verify(
            signature, f"{parts[0]}.{parts[1]}".encode("ascii")
        )
    except (InvalidSignature, ValueError) as exc:
        raise LicenseError(LicenseStatus.INVALID_SIGNATURE) from exc

    try:
        claims = LicenseClaims.from_dict(data, kid=kid)
    except InvalidClaimsError as exc:
        raise LicenseError(LicenseStatus.MALFORMED) from exc
    if claims.lid in revoked:
        raise LicenseError(LicenseStatus.REVOKED)
    return claims
