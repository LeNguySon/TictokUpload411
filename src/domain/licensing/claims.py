"""Signed license claims and validation outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.domain.licensing.plans import Plan


class LicenseStatus(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    MALFORMED = "malformed"
    INVALID_SIGNATURE = "invalid_signature"
    WRONG_MACHINE = "wrong_machine"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CLOCK_TAMPERED = "clock_tampered"


STATUS_MESSAGES: dict[LicenseStatus, str] = {
    LicenseStatus.VALID: "Bản quyền hợp lệ.",
    LicenseStatus.MISSING: "Ứng dụng chưa được kích hoạt bản quyền.",
    LicenseStatus.MALFORMED: "Key bản quyền không đúng định dạng.",
    LicenseStatus.INVALID_SIGNATURE: "Key bản quyền không hợp lệ (chữ ký sai).",
    LicenseStatus.WRONG_MACHINE: "Key này được cấp cho máy khác. Hãy gửi mã máy bên dưới để được cấp key mới.",
    LicenseStatus.EXPIRED: "Bản quyền đã hết hạn. Hãy gia hạn để tiếp tục sử dụng.",
    LicenseStatus.REVOKED: "Key bản quyền đã bị thu hồi.",
    LicenseStatus.CLOCK_TAMPERED: "Đồng hồ hệ thống bị lùi bất thường. Hãy chỉnh lại ngày giờ chính xác.",
}


class InvalidClaimsError(ValueError):
    pass


@dataclass(frozen=True)
class LicenseClaims:
    lid: str
    sub: str
    plan: Plan
    iat: int
    exp: int
    mid: str
    kid: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], kid: str) -> LicenseClaims:
        try:
            claims = cls(
                lid=str(data["lid"]),
                sub=str(data["sub"]),
                plan=Plan(data["plan"]),
                iat=int(data["iat"]),
                exp=int(data["exp"]),
                mid=str(data["mid"]),
                kid=str(kid),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidClaimsError(str(exc)) from exc
        if not claims.lid or not claims.mid or claims.exp <= claims.iat:
            raise InvalidClaimsError("incomplete claims")
        return claims


@dataclass(frozen=True)
class LicenseState:
    status: LicenseStatus
    claims: LicenseClaims | None = None

    @property
    def ok(self) -> bool:
        return self.status is LicenseStatus.VALID

    @property
    def message(self) -> str:
        return STATUS_MESSAGES[self.status]
