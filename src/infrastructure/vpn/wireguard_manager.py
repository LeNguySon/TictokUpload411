"""
WireGuard Configuration Manager & Parser for Antidetect Layered Tunneling.
Parses standard .conf files, generates interface/peer specs, and validates configs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WireGuardConfig:
    """WireGuard profile configuration representation."""

    private_key: str
    address: str
    peer_public_key: str
    endpoint: str
    dns: str | None = "1.1.1.1"
    allowed_ips: str = "0.0.0.0/0"
    persistent_keepalive: int = 25
    name: str | None = None

    def to_conf(self) -> str:
        """Serializes to standard WireGuard .conf file format."""
        lines = [
            "[Interface]",
            f"PrivateKey = {self.private_key}",
            f"Address = {self.address}",
        ]
        if self.dns:
            lines.append(f"DNS = {self.dns}")

        lines.extend(
            [
                "",
                "[Peer]",
                f"PublicKey = {self.peer_public_key}",
                f"Endpoint = {self.endpoint}",
                f"AllowedIPs = {self.allowed_ips}",
                f"PersistentKeepalive = {self.persistent_keepalive}",
            ]
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serializes configuration to dictionary."""
        return {
            "name": self.name,
            "private_key": self.private_key,
            "address": self.address,
            "peer_public_key": self.peer_public_key,
            "endpoint": self.endpoint,
            "dns": self.dns,
            "allowed_ips": self.allowed_ips,
            "persistent_keepalive": self.persistent_keepalive,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WireGuardConfig:
        """Deserializes configuration from dictionary."""
        return cls(
            name=data.get("name"),
            private_key=data.get("private_key", ""),
            address=data.get("address", "10.0.0.2/32"),
            peer_public_key=data.get("peer_public_key", ""),
            endpoint=data.get("endpoint", ""),
            dns=data.get("dns", "1.1.1.1"),
            allowed_ips=data.get("allowed_ips", "0.0.0.0/0"),
            persistent_keepalive=int(data.get("persistent_keepalive", 25)),
        )

    @classmethod
    def from_conf(cls, conf_text_or_path: str | Path, name: str | None = None) -> WireGuardConfig:
        """Parses a WireGuard .conf file or raw configuration text."""
        if isinstance(conf_text_or_path, Path) or (
            isinstance(conf_text_or_path, str) and "\n" not in conf_text_or_path and Path(conf_text_or_path).exists()
        ):
            text = Path(conf_text_or_path).read_text(encoding="utf-8")
            if not name:
                name = Path(conf_text_or_path).stem
        else:
            text = str(conf_text_or_path)

        priv_key = ""
        address = "10.0.0.2/32"
        dns = "1.1.1.1"
        pub_key = ""
        endpoint = ""
        allowed_ips = "0.0.0.0/0"
        keepalive = 25

        current_section = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue

            clean_line = re.split(r"[#;]", line, maxsplit=1)[0].strip()
            if not clean_line:
                continue

            if clean_line.startswith("[") and clean_line.endswith("]"):
                current_section = clean_line[1:-1].strip().lower()
                continue

            if "=" in clean_line:
                k, v = clean_line.split("=", 1)
                key = k.strip().lower()
                val = v.strip()

                if current_section == "interface":
                    if key == "privatekey":
                        priv_key = val
                    elif key == "address":
                        address = val
                    elif key == "dns":
                        dns = val
                elif current_section == "peer":
                    if key == "publickey":
                        pub_key = val
                    elif key == "endpoint":
                        endpoint = val
                    elif key == "allowedips":
                        allowed_ips = val
                    elif key == "persistentkeepalive":
                        try:
                            keepalive = int(val)
                        except ValueError:
                            keepalive = 25

        return cls(
            name=name,
            private_key=priv_key,
            address=address,
            peer_public_key=pub_key,
            endpoint=endpoint,
            dns=dns,
            allowed_ips=allowed_ips,
            persistent_keepalive=keepalive,
        )


class WireGuardManager:
    """Helper service for WireGuard validation and management."""

    @staticmethod
    def validate_conf(conf_text: str) -> bool:
        """Validates that a configuration text has the required fields."""
        try:
            cfg = WireGuardConfig.from_conf(conf_text)
            return bool(cfg.private_key and cfg.peer_public_key and cfg.endpoint)
        except Exception:
            return False

    @staticmethod
    def parse(conf_text_or_path: str | Path, name: str | None = None) -> WireGuardConfig:
        """Parses WireGuard configuration text or file."""
        return WireGuardConfig.from_conf(conf_text_or_path, name=name)
