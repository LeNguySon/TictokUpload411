"""
Proxy Domain Model representing an outbound proxy entity with format conversion and leak detection.
"""

from dataclasses import dataclass
from enum import StrEnum

from sammonny.core.models import ProxyItem


class ProxyType(StrEnum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class ProxyStatus(StrEnum):
    UNCHECKED = "unchecked"
    ALIVE = "alive"
    DEAD = "dead"
    LEAK_DETECTED = "leak_detected"


@dataclass
class ProxyDomainModel:
    id: int
    scheme: ProxyType
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    change_ip_url: str | None = None
    status: ProxyStatus = ProxyStatus.UNCHECKED
    latency_ms: float = -1.0
    country: str | None = None
    city: str | None = None
    last_checked_at: str | None = None

    @property
    def supports_rotation(self) -> bool:
        return bool(self.change_ip_url and self.change_ip_url.strip())

    def to_export_format(self) -> str:
        """Exports proxy into standard host:port[:user:pass] format."""
        if self.username and self.password:
            return f"{self.host}:{self.port}:{self.username}:{self.password}"
        return f"{self.host}:{self.port}"

    def to_uri(self) -> str:
        """Generates standard RFC URL representation."""
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"{self.scheme.value}://{auth}{self.host}:{self.port}"

    def to_sammonny_item(self) -> ProxyItem:
        """Converts into SamMonny SDK ProxyItem object."""
        return ProxyItem(
            id=str(self.id),
            mode=self.scheme.value,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            change_ip_url=self.change_ip_url,
            is_alive=(self.status == ProxyStatus.ALIVE),
            latency_ms=self.latency_ms if self.latency_ms > 0 else None,
            country=self.country,
        )
