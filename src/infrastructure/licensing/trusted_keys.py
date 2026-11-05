"""Public keys trusted to sign licenses (kid -> base64 raw Ed25519 public key) and revoked license ids.

Public keys are not secret. Add a new kid here when rotating the signing key; to revoke a key in offline
mode add its ``lid`` to REVOKED_LICENSE_IDS and ship an update.
"""

TRUSTED_PUBLIC_KEYS: dict[str, str] = {
    "k2026a": "fy7qdMQBKuIzjbYA51pg1gjtOmrBstcrsmooGp3+lUY=",
}

REVOKED_LICENSE_IDS: frozenset[str] = frozenset()
