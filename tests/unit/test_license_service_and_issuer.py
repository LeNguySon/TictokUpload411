"""License service (machine binding, expiry, clock guard, activation) and the developer issuer tool."""

from __future__ import annotations

import csv
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.application.services.license_service import CLOCK_TOLERANCE_S, LicenseService
from src.domain.licensing import entitlements
from src.domain.licensing.claims import LicenseStatus
from src.domain.licensing.plans import Feature
from src.infrastructure.licensing.license_store import LicenseStore
from src.infrastructure.licensing.verifier import decode_and_verify, encode_license, public_key_b64

DAY = 86400
MID = "1111-2222-3333-4444"


@pytest.fixture
def env(tmp_path):
    sk = Ed25519PrivateKey.generate()
    now = [float(time.time())]
    store = LicenseStore(tmp_path / "license.dat")

    def make(revoked=()):
        return LicenseService(
            store=store,
            trusted={"k1": public_key_b64(sk)},
            revoked=revoked,
            machine_code_fn=lambda: MID,
            clock=lambda: now[0],
        )

    def key(**over):
        claims = {"lid": "lic-1", "sub": "Khách A", "plan": "upload", "iat": int(now[0]) - DAY,
                  "exp": int(now[0]) + 10 * DAY, "mid": MID}
        claims.update(over)
        return encode_license(claims, sk, kid="k1")

    return make, key, store, now


def test_missing_license(env):
    make, _, _, _ = env
    state = make().validate()
    assert state.status is LicenseStatus.MISSING and entitlements.current() is None


def test_activate_valid_key_saves_and_unlocks(env):
    make, key, store, _ = env
    state = make().activate(key())
    assert state.ok and store.load_key() == key()
    assert entitlements.has(Feature.UPLOAD) and not entitlements.has(Feature.CHANNEL_HEALTH)
    assert make().validate().ok  # persisted


@pytest.mark.parametrize(
    ("over", "status"),
    [
        ({"mid": "9999-9999-9999-9999"}, LicenseStatus.WRONG_MACHINE),
        ({"exp": int(time.time()) - 60}, LicenseStatus.EXPIRED),
    ],
)
def test_invalid_key_is_not_saved_and_locks(env, over, status):
    make, key, store, _ = env
    state = make().activate(key(**over))
    assert state.status is status and store.load_key() is None and entitlements.current() is None


def test_revoked_license(env):
    make, key, _, _ = env
    assert make(revoked={"lic-1"}).activate(key()).status is LicenseStatus.REVOKED


def test_clock_rolled_back_is_detected(env):
    make, key, store, now = env
    assert make().activate(key()).ok
    store.touch(now[0] + 5 * DAY)  # the app saw this time earlier
    assert make().validate().status is LicenseStatus.CLOCK_TAMPERED
    now[0] += 5 * DAY - CLOCK_TOLERANCE_S / 2  # small drift is tolerated
    assert make().validate().ok


def test_clock_before_issue_date_is_detected(env):
    make, key, _, now = env
    assert make().activate(key(iat=int(now[0]) + 3 * DAY, exp=int(now[0]) + 30 * DAY)).status is (
        LicenseStatus.CLOCK_TAMPERED
    )


def test_runtime_check_expires_while_running(env):
    make, key, _, now = env
    svc = make()
    assert svc.activate(key()).ok and svc.runtime_check().ok
    now[0] += 11 * DAY
    state = svc.runtime_check()
    assert state.status is LicenseStatus.EXPIRED and entitlements.current() is None


def test_validate_records_last_seen(env):
    make, key, store, now = env
    make().activate(key())
    assert store.last_seen() == pytest.approx(now[0])


# --- issuer tool
def test_issuer_keygen_issue_and_verify(tmp_path):
    from tools.license_issuer import issuer

    home = tmp_path / "issuer"
    kid, pub = issuer.keygen(home, kid="t1")
    key_file = home / "signing_keys" / "t1.key"
    assert key_file.exists() and b"PRIVATE KEY" not in key_file.read_bytes()

    lic = issuer.issue(home, kid="t1", sub="Khách B", plan="pro", mid=MID, days=30, note="test")
    claims = decode_and_verify(lic, {kid: pub})
    assert claims.sub == "Khách B" and claims.mid == MID and claims.exp - claims.iat == 30 * DAY

    rows = list(csv.DictReader((home / "issued_licenses.csv").open(encoding="utf-8")))
    assert rows[0]["lid"] == claims.lid and rows[0]["plan"] == "pro" and "TAVM1" not in str(rows)


def test_issuer_rejects_bad_input(tmp_path):
    from tools.license_issuer import issuer

    home = tmp_path / "issuer"
    issuer.keygen(home, kid="t1")
    with pytest.raises(ValueError):
        issuer.issue(home, kid="t1", sub="X", plan="gold", mid=MID, days=30)
    with pytest.raises(ValueError):
        issuer.issue(home, kid="t1", sub="X", plan="pro", mid="not-a-code", days=30)
    with pytest.raises(FileExistsError):
        issuer.keygen(home, kid="t1")  # never overwrite a signing key


def test_issuer_backup_restore(tmp_path):
    from tools.license_issuer import issuer

    home, other = tmp_path / "a", tmp_path / "b"
    _, pub = issuer.keygen(home, kid="t1")
    backup = tmp_path / "t1.pem"
    issuer.backup(home, "t1", backup, password=b"correct horse")
    assert b"ENCRYPTED PRIVATE KEY" in backup.read_bytes()
    issuer.restore(other, "t1", backup, password=b"correct horse")
    lic = issuer.issue(other, kid="t1", sub="C", plan="profile", mid=MID, days=1)
    assert decode_and_verify(lic, {"t1": pub}).sub == "C"


def test_app_never_imports_issuer_tool():
    from pathlib import Path

    for py in Path("src").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "tools.license_issuer" not in text, py
        assert "PRIVATE KEY-----" not in text, py
