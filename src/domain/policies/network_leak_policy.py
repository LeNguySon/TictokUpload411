"""
Network Leak Policy (AgentShield Tier-1 Security Rule).
Verifies that outbound proxy egress IP does not match any local machine/host IP address.
"""

import socket
from dataclasses import dataclass


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
        self.known_host_ips: set[str] = set(known_host_ips) if known_host_ips else self._discover_local_ips()

    @staticmethod
    def _discover_local_ips() -> set[str]:
        ips = {"127.0.0.1", "localhost", "::1"}
        try:
            hostname = socket.gethostname()
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip = item[4][0]
                ips.add(ip)
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
