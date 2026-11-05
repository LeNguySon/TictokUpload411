"""
Profile Import Parser supporting standard TikTok MMO format and customizable field sequences.
Clean Architecture: Application Layer (Parsers).
"""

import time
from typing import Any

FIELD_ALIASES: dict[str, str] = {
    # User / Name
    "user": "user",
    "username": "user",
    "name": "user",
    "tên": "user",
    "ten": "user",
    "profile": "user",
    "profile_name": "user",
    "tên hồ sơ": "user",
    # Pass
    "pass": "pass",
    "password": "pass",
    "mật khẩu": "pass",
    "matkhau": "pass",
    "pass_tt": "pass",
    # Cookie TikTok
    "cookie": "cookie",
    "cookie tiktok": "cookie",
    "cookietiktok": "cookie",
    "cookie_tiktok": "cookie",
    "cookie_tt": "cookie",
    # Email
    "email": "email",
    "mail": "email",
    # Passmail
    "passmail": "pass_mail",
    "pass_mail": "pass_mail",
    "mật khẩu email": "pass_mail",
    "mật khẩu mail": "pass_mail",
    "matkhaumail": "pass_mail",
    "email_password": "pass_mail",
    # RefreshToken
    "refreshtoken": "refresh_token",
    "refresh_token": "refresh_token",
    "rt": "refresh_token",
    # ClientId
    "clientid": "client_id",
    "client_id": "client_id",
    "cid": "client_id",
    # Cookie Email
    "cookie email": "cookie_email",
    "cookieemail": "cookie_email",
    "cookie_email": "cookie_email",
    "mail_cookie": "cookie_email",
    # Proxy & Note & 2FA
    "proxy": "proxy",
    "proxy_raw": "proxy",
    "note": "note",
    "ghi chú": "note",
    "ghichu": "note",
    "2fa": "2fa",
    "totp": "2fa",
}

PRESETS: dict[str, dict[str, Any]] = {
    "mmo_8_fields": {
        "label": "Chuẩn TikTok MMO (8 trường): User | Pass | Cookie TikTok | Email | Passmail | RefreshToken | ClientId | Cookie Email",
        "tokens": ["user", "pass", "cookie", "email", "pass_mail", "refresh_token", "client_id", "cookie_email"],
        "delimiter": "|",
    },
    "legacy_5_fields": {
        "label": "Chuẩn Cũ (5 trường): Tên | Proxy | Cookie | Email | Ghi chú",
        "tokens": ["user", "proxy", "cookie", "email", "note"],
        "delimiter": "|",
    },
    "basic_3_fields": {
        "label": "Cơ Bản (3 trường): User | Pass | Cookie TikTok",
        "tokens": ["user", "pass", "cookie"],
        "delimiter": "|",
    },
    "account_mail_4_fields": {
        "label": "Tài Khoản & Mail (4 trường): User | Pass | Email | Passmail",
        "tokens": ["user", "pass", "email", "pass_mail"],
        "delimiter": "|",
    },
    "cookie_only": {
        "label": "Chỉ Cookie: Cookie TikTok (1 dòng / 1 cookie)",
        "tokens": ["cookie"],
        "delimiter": "|",
    },
}


class ProfileImportParser:
    """
    High-performance parser for bulk TikTok account import strings.
    Translates raw delimited text into structured dictionaries.
    """

    @classmethod
    def normalize_field_name(cls, raw_field: str) -> str:
        clean = raw_field.strip().lower().replace("{", "").replace("}", "")
        return FIELD_ALIASES.get(clean, clean)

    @classmethod
    def parse_template_tokens(cls, template: str, delimiter: str = "|") -> list[str]:
        raw_parts = template.split(delimiter)
        return [cls.normalize_field_name(p) for p in raw_parts if p.strip()]

    @classmethod
    def parse_line(
        cls,
        line: str,
        format_name: str = "mmo_8_fields",
        custom_template: str | None = None,
        delimiter: str = "|",
        default_name_prefix: str = "TikTok",
    ) -> dict[str, Any] | None:
        raw = line.strip()
        if not raw:
            return None

        # Resolve tokens order
        if custom_template:
            tokens = cls.parse_template_tokens(custom_template, delimiter)
        elif format_name in PRESETS:
            preset = PRESETS[format_name]
            tokens = preset["tokens"]
            delimiter = delimiter or preset["delimiter"]
        else:
            tokens = PRESETS["mmo_8_fields"]["tokens"]

        # Special Case: Raw cookie string without delimiters
        if delimiter not in raw:
            if "msToken=" in raw or "sessionid=" in raw or raw.startswith("["):
                auto_name = f"{default_name_prefix}_{int(time.time() * 1000) % 100000}"
                return {
                    "user": auto_name,
                    "pass": None,
                    "cookie": raw,
                    "email": None,
                    "pass_mail": None,
                    "refresh_token": None,
                    "client_id": None,
                    "cookie_email": None,
                    "proxy": None,
                    "note": None,
                }
            else:
                return {
                    "user": raw,
                    "pass": None,
                    "cookie": None,
                    "email": None,
                    "pass_mail": None,
                    "refresh_token": None,
                    "client_id": None,
                    "cookie_email": None,
                    "proxy": None,
                    "note": None,
                }

        parts = [p.strip() for p in raw.split(delimiter)]
        result: dict[str, Any] = {
            "user": None,
            "pass": None,
            "cookie": None,
            "email": None,
            "pass_mail": None,
            "refresh_token": None,
            "client_id": None,
            "cookie_email": None,
            "proxy": None,
            "note": None,
        }

        for idx, token_key in enumerate(tokens):
            if idx < len(parts):
                val = parts[idx]
                result[token_key] = val if val else None

        # Ensure user has a valid fallback name
        if not result.get("user"):
            auto_name = f"{default_name_prefix}_{int(time.time() * 1000) % 100000}"
            result["user"] = auto_name

        return result

