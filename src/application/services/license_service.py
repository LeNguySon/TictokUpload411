"""Offline license validation: signature, machine binding, expiry and clock-rollback guard.

On every outcome the process-wide entitlements are updated: valid -> claims, anything else -> locked.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Collection, Mapping

from src.domain.licensing import entitlements
from src.domain.licensing.claims import LicenseClaims, LicenseState, LicenseStatus
from src.infrastructure.licensing.license_store import LicenseStore
from src.infrastructure.licensing.machine_id import machine_code
from src.infrastructure.licensing.trusted_keys import REVOKED_LICENSE_IDS, TRUSTED_PUBLIC_KEYS
from src.infrastructure.licensing.verifier import LicenseError, decode_and_verify, normalize_key

logger = logging.getLogger(__name__)

CLOCK_TOLERANCE_S = 24 * 3600  # time-zone changes / NTP corrections are not tampering


class LicenseService:
    def __init__(
        self,
        store: LicenseStore | None = None,
        trusted: Mapping[str, str] | None = None,
        revoked: Collection[str] | None = None,
        machine_code_fn: Callable[[], str] = machine_code,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store or LicenseStore()
        self.trusted = TRUSTED_PUBLIC_KEYS if trusted is None else trusted
        self.revoked = REVOKED_LICENSE_IDS if revoked is None else revoked
        self._machine_code_fn = machine_code_fn
        self._machine_code: str | None = None
        self.clock = clock
        self._state = LicenseState(LicenseStatus.MISSING)

    @property
    def state(self) -> LicenseState:
        return self._state

    def machine_code(self) -> str:
        if self._machine_code is None:
            self._machine_code = self._machine_code_fn()
        return self._machine_code

    def validate(self) -> LicenseState:
        """Validates the stored key (startup)."""
        key = self.store.load_key()
        if not key:
            return self._apply(LicenseState(LicenseStatus.MISSING))
        return self._apply(self._evaluate(key))

    def activate(self, key: str) -> LicenseState:
        """Validates a pasted key; it is stored only when valid for this machine."""
        state = self._evaluate(key)
        if state.ok:
            self.store.save_key(normalize_key(key))
        return self._apply(state)

    def runtime_check(self) -> LicenseState:
        """Cheap periodic check of the already-validated license (no I/O): catches expiry while running."""
        claims = self._state.claims
        if self._state.ok and claims is not None and self.clock() >= claims.exp:
            return self._apply(LicenseState(LicenseStatus.EXPIRED, claims))
        return self._state

    def record_seen_time(self) -> None:
        """Persists the current time for rollback detection (file I/O: run off the GUI thread)."""
        try:
            self.store.touch(self.clock())
        except Exception as exc:
            logger.warning("Could not record license clock: %s", exc)

    def _evaluate(self, key: str) -> LicenseState:
        try:
            claims: LicenseClaims = decode_and_verify(key, self.trusted, self.revoked)
        except LicenseError as exc:
            return LicenseState(exc.status)

        if claims.mid != self.machine_code():
            return LicenseState(LicenseStatus.WRONG_MACHINE, claims)
        now = self.clock()
        last_seen = self.store.last_seen()
        if (last_seen is not None and now < last_seen - CLOCK_TOLERANCE_S) or now < claims.iat - CLOCK_TOLERANCE_S:
            return LicenseState(LicenseStatus.CLOCK_TAMPERED, claims)
        if now >= claims.exp:
            return LicenseState(LicenseStatus.EXPIRED, claims)
        self.record_seen_time()
        return LicenseState(LicenseStatus.VALID, claims)

    def _apply(self, state: LicenseState) -> LicenseState:
        self._state = state
        entitlements.set_current(state.claims if state.ok else None)
        if not state.ok:
            logger.warning("License not valid: %s", state.status.value)
        return state
