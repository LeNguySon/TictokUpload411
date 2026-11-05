"""TAVM license issuer (developer only — do NOT ship with the app).

The Ed25519 signing key is stored DPAPI-encrypted for the current Windows user under the issuer home
(default ``%LOCALAPPDATA%\\TAVM-Issuer``, override with ``TAVM_ISSUER_HOME``), never in the repository.
Back it up with ``backup`` (password-encrypted PEM): losing it means no new keys can be issued for the
public key compiled into the app.

Usage:
    python -m tools.license_issuer.issuer keygen [--kid K]
    python -m tools.license_issuer.issuer issue --kid K --sub "Tên khách" --plan pro --mid XXXX-XXXX-XXXX-XXXX --days 30
    python -m tools.license_issuer.issuer issue ... --until 2027-12-31
    python -m tools.license_issuer.issuer backup --kid K --out D:\\backup\\K.pem
    python -m tools.license_issuer.issuer restore --kid K --in D:\\backup\\K.pem
    python -m tools.license_issuer.issuer list
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.domain.licensing.plans import PLAN_DISPLAY_NAMES, Plan
from src.infrastructure.credentials.dpapi import protect_bytes, unprotect_bytes
from src.infrastructure.licensing.verifier import encode_license, public_key_b64

_PURPOSE = "tavm-license-signing-v1"
_MID_RE = re.compile(r"^[0-9A-F]{4}(-[0-9A-F]{4}){3}$")
_LEDGER_FIELDS = ["issued_at", "lid", "kid", "sub", "plan", "mid", "expires", "note"]
DAY = 86400


def default_home() -> Path:
    override = os.environ.get("TAVM_ISSUER_HOME")
    if override:
        return Path(override)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TAVM-Issuer"


def _key_path(home: Path, kid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", kid):
        raise ValueError("kid must be 1-32 chars of letters, digits, '-' or '_'")
    return Path(home) / "signing_keys" / f"{kid}.key"


def _save_private(home: Path, kid: str, sk: Ed25519PrivateKey) -> None:
    path = _key_path(home, kid)
    if path.exists():
        raise FileExistsError(f"Signing key {kid} already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    path.write_bytes(protect_bytes(raw, _PURPOSE))


def _load_private(home: Path, kid: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(unprotect_bytes(_key_path(home, kid).read_bytes(), _PURPOSE))


def keygen(home: Path, kid: str | None = None) -> tuple[str, str]:
    """Creates a signing key; returns (kid, public key) to put in src/infrastructure/licensing/trusted_keys.py."""
    kid = kid or datetime.now().strftime("k%Y%m%d")
    sk = Ed25519PrivateKey.generate()
    _save_private(home, kid, sk)
    return kid, public_key_b64(sk)


def public_key(home: Path, kid: str) -> str:
    return public_key_b64(_load_private(home, kid))


def _expiry(days: int | None, until: str | None, now: float) -> int:
    if (days is None) == (until is None):
        raise ValueError("Give exactly one of days / until")
    if days is not None:
        if days <= 0:
            raise ValueError("days must be positive")
        return int(now) + days * DAY
    end = datetime.strptime(str(until), "%Y-%m-%d") + timedelta(days=1)  # valid through that whole local day
    exp = int(end.timestamp())
    if exp <= now:
        raise ValueError("until must be in the future")
    return exp


def issue(
    home: Path,
    kid: str,
    sub: str,
    plan: str,
    mid: str,
    days: int | None = None,
    until: str | None = None,
    note: str = "",
) -> str:
    try:
        plan_value = Plan(plan).value
    except ValueError as exc:
        raise ValueError(f"Unknown plan {plan!r}; use one of {[p.value for p in Plan]}") from exc
    mid = mid.strip().upper()
    if not _MID_RE.match(mid):
        raise ValueError("Machine code must look like XXXX-XXXX-XXXX-XXXX (shown in the app's activation dialog)")
    if not sub.strip():
        raise ValueError("Customer name (sub) is required")
    now = time.time()
    claims = {
        "lid": str(uuid.uuid4()),
        "sub": sub.strip(),
        "plan": plan_value,
        "iat": int(now),
        "exp": _expiry(days, until, now),
        "mid": mid,
    }
    key = encode_license(claims, _load_private(home, kid), kid=kid)
    _append_ledger(home, claims, kid, note)
    return key


def _append_ledger(home: Path, claims: dict, kid: str, note: str) -> None:
    ledger = Path(home) / "issued_licenses.csv"
    new = not ledger.exists()
    with ledger.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_LEDGER_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(
            {
                "issued_at": datetime.fromtimestamp(claims["iat"]).isoformat(timespec="seconds"),
                "lid": claims["lid"],
                "kid": kid,
                "sub": claims["sub"],
                "plan": claims["plan"],
                "mid": claims["mid"],
                "expires": datetime.fromtimestamp(claims["exp"]).isoformat(timespec="seconds"),
                "note": note,
            }
        )


def backup(home: Path, kid: str, out: Path, password: bytes) -> None:
    if len(password) < 8:
        raise ValueError("Backup password must be at least 8 characters")
    pem = _load_private(home, kid).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )
    Path(out).write_bytes(pem)


def restore(home: Path, kid: str, src: Path, password: bytes) -> None:
    sk = serialization.load_pem_private_key(Path(src).read_bytes(), password=password)
    if not isinstance(sk, Ed25519PrivateKey):
        raise ValueError("Backup is not an Ed25519 signing key")
    _save_private(home, kid, sk)


def _ask_password(confirm: bool) -> bytes:
    pw = getpass.getpass("Backup password: ")
    if confirm and pw != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    return pw.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TAVM license issuer (developer only)")
    parser.add_argument("--home", type=Path, default=default_home())
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("keygen")
    p.add_argument("--kid")
    p = sub.add_parser("pubkey")
    p.add_argument("--kid", required=True)
    p = sub.add_parser("issue")
    p.add_argument("--kid", required=True)
    p.add_argument("--sub", required=True, help="Customer display name")
    p.add_argument("--plan", required=True, choices=[x.value for x in Plan])
    p.add_argument("--mid", required=True, help="Machine code from the customer's activation dialog")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--days", type=int)
    group.add_argument("--until", help="Last valid day, YYYY-MM-DD")
    p.add_argument("--note", default="")
    p = sub.add_parser("backup")
    p.add_argument("--kid", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("restore")
    p.add_argument("--kid", required=True)
    p.add_argument("--in", dest="src", type=Path, required=True)
    sub.add_parser("list")
    args = parser.parse_args(argv)

    if args.cmd == "keygen":
        kid, pub = keygen(args.home, args.kid)
        print(f"Signing key created: {kid}\nAdd to TRUSTED_PUBLIC_KEYS: {kid!r}: {pub!r}")
        print("Back it up now: issuer backup --kid", kid, "--out <file>")
    elif args.cmd == "pubkey":
        print(public_key(args.home, args.kid))
    elif args.cmd == "issue":
        key = issue(args.home, args.kid, args.sub, args.plan, args.mid, args.days, args.until, args.note)
        print(f"{PLAN_DISPLAY_NAMES[Plan(args.plan)]} for {args.sub} ({args.mid}):\n\n{key}\n")
    elif args.cmd == "backup":
        backup(args.home, args.kid, args.out, _ask_password(confirm=True))
        print("Encrypted backup written:", args.out)
    elif args.cmd == "restore":
        restore(args.home, args.kid, args.src, _ask_password(confirm=False))
        print("Signing key restored:", args.kid)
    elif args.cmd == "list":
        ledger = Path(args.home) / "issued_licenses.csv"
        print(ledger.read_text(encoding="utf-8") if ledger.exists() else "No licenses issued yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
