"""
Network Leak Policy (AgentShield Tier-1 Security Rule).
Verifies that outbound proxy egress IP does not match any local machine/host IP address.
"""

import socket
import time
import urllib.request
from dataclasses import dataclass

_PUBLIC_IP_SERVICES = ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com")
_PUBLIC_IP_CACHE: dict[str, tuple[float, str | None]] = {}
_PUBLIC_IP_TTL_S = 30 * 60


def discover_public_ip(timeout: float = 5.0) -> str | None:
    """The machine's own public IP (direct request, no account data), cached for 30 minutes.

    Local interface addresses are private (192.168.x.x behind NAT): without the public IP a proxy that
    exits through the host connection could never be detected.
    """
    cached = _PUBLIC_IP_CACHE.get("ip")
    if cached and time.monotonic() - cached[0] < _PUBLIC_IP_TTL_S:
        return cached[1]
    ip: str | None = None
    for url in _PUBLIC_IP_SERVICES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TAVM-LeakGuard/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read(64).decode("ascii", "ignore").strip()
            socket.inet_pton(socket.AF_INET6 if ":" in text else socket.AF_INET, text)
            ip = text
            break
        except Exception:
            continue
    _PUBLIC_IP_CACHE["ip"] = (time.monotonic(), ip)
    return ip


@dataclass(frozen=True)
class LeakAuditResult:
    is_safe: bool
    leak_detected: bool
    egress_ip: str | None
    reason: str


class NetworkLeakPolicy:
    """
    Guards against catastrophic traffic leaks by checking proxy exit IP.
    If proxy fails open and reveals host IP, upload is immediately halted.
    """

    def __init__(self, known_host_ips: set[str] | None = None) -> None:
        self._needs_public_ip = not known_host_ips
        self.known_host_ips: set[str] = set(known_host_ips) if known_host_ips else self._discover_local_ips()

    @staticmethod
    def _discover_local_ips() -> set[str]:
        ips = {"127.0.0.1", "localhost", "::1"}
        try:
            hostname = socket.gethostname()
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip = item[4][0]
                ips.add(str(ip))
        except Exception:
            pass
        return ips

    def evaluate(self, proxy_egress_ip: str | None) -> LeakAuditResult:
        if not proxy_egress_ip:
            return LeakAuditResult(
                is_safe=False,
                leak_detected=False,
                egress_ip=None,
                reason="Unable to determine proxy egress IP",
            )

        if self._needs_public_ip:
            # Lazily (evaluate runs in proxy-check workers, never at window start-up).
            self._needs_public_ip = False
            public_ip = discover_public_ip()
            if public_ip:
                self.known_host_ips.add(public_ip)
        cleaned_ip = proxy_egress_ip.strip()

        if cleaned_ip in self.known_host_ips:
            return LeakAuditResult(
                is_safe=False,
                leak_detected=True,
                egress_ip=cleaned_ip,
                reason=f"Critical IP Leak Detected! Outbound egress {cleaned_ip} matches local machine host IP.",
            )

        return LeakAuditResult(
            is_safe=True,
            leak_detected=False,
            egress_ip=cleaned_ip,
            reason="Proxy egress IP is verified and distinct from host machine.",
        )
