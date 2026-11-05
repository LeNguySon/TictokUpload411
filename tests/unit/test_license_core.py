"""Licensing core: plans/features, signed key format, offline verification, machine code, store, clock guard."""

from __future__ import annotations

import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.domain.licensing import entitlements
from src.domain.licensing.claims import LicenseClaims, LicenseStatus
from src.domain.licensing.plans import Feature, Plan, plan_features
from src.infrastructure.licensing.license_store import LicenseStore
from src.infrastructure.licensing.machine_id import format_machine_code, machine_code
from src.infrastructure.licensing.verifier import (
    LicenseError,
    decode_and_verify,
    encode_license,
    public_key_b64,
)

DAY = 86400


@pytest.fixture
def signing():
    sk = Ed25519PrivateKey.generate()
    return sk, {"k1": public_key_b64(sk)}


def _claims(**over):
    now = int(time.time())
    base = {"lid": "lic-0001", "sub": "Khách A", "plan": "upload", "iat": now - DAY, "exp": now + 30 * DAY,
            "mid": "AAAA-BBBB-CCCC-DDDD"}
    base.update(over)
    return base


# --- plans
def test_plans_are_cumulative():
    assert plan_features(Plan.PROFILE) == {Feature.PROFILES}
    assert plan_features(Plan.UPLOAD) == {Feature.PROFILES, Feature.UPLOAD}
    assert plan_features(Plan.PRO) == {Feature.PROFILES, Feature.UPLOAD, Feature.CHANNEL_HEALTH}


def test_entitlements_require(monkeypatch):
    claims = LicenseClaims.from_dict(_claims(plan="profile"), kid="k1")
    entitlements.set_current(claims)
    assert entitlements.has(Feature.PROFILES) and not entitlements.has(Feature.UPLOAD)
    with pytest.raises(entitlements.LicenseFeatureError):
        entitlements.require(Feature.UPLOAD)
    entitlements.set_current(None)
    assert not entitlements.has(Feature.PROFILES)


# --- key format / signature
def test_roundtrip_and_whitespace_tolerant(signing):
    sk, trusted = signing
    key = encode_license(_claims(), sk, kid="k1")
    assert key.startswith("TAVM1.")
    pasted = "\n  ".join(key[i : i + 40] for i in range(0, len(key), 40))
    claims = decode_and_verify(pasted, trusted)
    assert claims.sub == "Khách A" and claims.plan is Plan.UPLOAD and claims.kid == "k1"


def test_tampered_payload_rejected(signing):
    sk, trusted = signing
    key = encode_license(_claims(plan="upload"), sk, kid="k1")
    prefix, payload, sig = key.split(".")
    forged = encode_license(_claims(plan="pro"), sk, kid="k1").split(".")[1]
    with pytest.raises(LicenseError) as e:
        decode_and_verify(f"{prefix}.{forged}.{sig}", trusted)
    assert e.value.status is LicenseStatus.INVALID_SIGNATURE


def test_other_signer_and_unknown_kid_rejected(signing):
    _, trusted = signing
    other = Ed25519PrivateKey.generate()
    with pytest.raises(LicenseError) as e:
        decode_and_verify(encode_license(_claims(), other, kid="k1"), trusted)
    assert e.value.status is LicenseStatus.INVALID_SIGNATURE
    with pytest.raises(LicenseError) as e:
        decode_and_verify(encode_license(_claims(), other, kid="zz"), trusted)
    assert e.value.status is LicenseStatus.INVALID_SIGNATURE


@pytest.mark.parametrize("junk", ["", "abc", "TAVM1.x", "TAVM2.a.b", "TAVM1.!!!.???"])
def test_malformed_rejected(signing, junk):
    with pytest.raises(LicenseError) as e:
        decode_and_verify(junk, signing[1])
    assert e.value.status is LicenseStatus.MALFORMED


def test_unknown_plan_rejected(signing):
    sk, trusted = signing
    with pytest.raises(LicenseError) as e:
        decode_and_verify(encode_license(_claims(plan="gold"), sk, kid="k1"), trusted)
    assert e.value.status is LicenseStatus.MALFORMED


# --- machine code
def test_machine_code_format_and_stability():
    a = format_machine_code("guid-1", "serial-1")
    assert a == format_machine_code("guid-1", "serial-1")
    assert a != format_machine_code("guid-2", "serial-1")
    parts = a.split("-")
    assert len(parts) == 4 and all(len(p) == 4 and p.isalnum() and p.upper() == p for p in parts)
    assert "guid-1" not in a  # only a hash is shown/sent
    real = machine_code()
    assert real == machine_code() and len(real) == 19


# --- store (DPAPI file) + last-seen clock
def test_store_roundtrip_is_encrypted(tmp_path):
    path = tmp_path / "license.dat"
    store = LicenseStore(path)
    assert store.load_key() is None
    store.save_key("TAVM1.secret-key-material.sig")
    assert b"secret-key-material" not in path.read_bytes()
    assert LicenseStore(path).load_key() == "TAVM1.secret-key-material.sig"


def test_store_last_seen_only_moves_forward(tmp_path):
    store = LicenseStore(tmp_path / "license.dat")
    store.touch(1000.0)
    store.touch(500.0)
    assert store.last_seen() == 1000.0


def test_corrupted_store_reads_as_empty(tmp_path):
    path = tmp_path / "license.dat"
    path.write_bytes(b"garbage")
    store = LicenseStore(path)
    assert store.load_key() is None and store.last_seen() is None
