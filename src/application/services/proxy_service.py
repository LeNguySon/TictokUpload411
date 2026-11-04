"""
Proxy Application Service orchestrating health checks, leak detection, and IP rotation.
"""

import logging
from typing import Any

import sammonny
from sammonny import ProxyHealthResult, ProxyItem

from src.domain.policies.network_leak_policy import NetworkLeakPolicy
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

logger = logging.getLogger(__name__)


class ProxyService:
    """
    Manages proxy operational health, enforces the AgentShield Network Leak Policy,
    and controls rotation endpoints.
    """

    def __init__(
        self,
        proxy_repo: ProxyRepository,
        leak_policy: NetworkLeakPolicy | None = None,
    ) -> None:
        self.proxy_repo = proxy_repo
        self.leak_policy = leak_policy or NetworkLeakPolicy()

    def _to_proxy_item(self, row: dict[str, Any]) -> ProxyItem:
        return ProxyItem(
            id=str(row["id"]),
            mode=row.get("scheme", "http"),
            host=row["host"],
            port=row["port"],
            username=row.get("username"),
            password=row.get("password"),
            change_ip_url=row.get("change_ip_url"),
            is_alive=(row.get("status") == "alive"),
            latency_ms=row.get("latency_ms") if row.get("latency_ms", -1) > 0 else None,
            country=row.get("country"),
        )

    def check_proxy(self, proxy_id: int) -> ProxyHealthResult:
        """
        Executes an active health check on a single proxy, audits egress IP for leaks,
        and synchronizes status to the database repository.
        """
        row = self.proxy_repo.get_by_id(proxy_id)
        if not row:
            raise ValueError(f"Proxy with ID {proxy_id} not found")

        item = self._to_proxy_item(row)
        health = sammonny.check_proxy_health(item)

        # AgentShield Tier-1 Critical IP Leak Audit
        if health.is_alive and health.egress_ip:
            audit = self.leak_policy.evaluate(health.egress_ip)
            if audit.leak_detected:
                logger.critical("LEAK DETECTED on proxy %s: %s", proxy_id, audit.reason)
                self.proxy_repo.mark_ip_leak(proxy_id, error_msg=audit.reason)
                return ProxyHealthResult(
                    is_alive=False,
                    latency_ms=-1.0,
                    egress_ip=health.egress_ip,
                    error=audit.reason,
                )

        # Update regular health status
        status = "alive" if health.is_alive else "dead"
        latency = int(health.latency_ms) if (health.is_alive and health.latency_ms is not None) else -1
        self.proxy_repo.update_health(
            proxy_id=proxy_id,
            status=status,
            latency_ms=latency,
            public_ip=health.egress_ip,
            country_code=health.country,
            city=health.city,
            timezone=health.timezone,
            error_message=health.error,
        )

        return health

    def rotate_proxy_ip(self, proxy_id: int) -> dict[str, Any]:
        """Triggers the remote rotation webhook if the proxy supports it."""
        row = self.proxy_repo.get_by_id(proxy_id)
        if not row:
            raise ValueError(f"Proxy with ID {proxy_id} not found")

        change_url = row.get("change_ip_url")
        if not change_url:
            raise ValueError(f"Proxy {proxy_id} does not have an IP rotation URL configured")

        item = self._to_proxy_item(row)
        return sammonny.trigger_ip_rotation(item)

    def change_rotating_ip(self, proxy_id: int) -> dict[str, Any]:
        """Alias for rotate_proxy_ip for backward compatibility."""
        return self.rotate_proxy_ip(proxy_id)

    def check_all_proxies(self) -> list[ProxyHealthResult]:
        """Performs sequential health checks for all stored proxies."""
        proxies = self.proxy_repo.list_all()
        results: list[ProxyHealthResult] = []
        for p in proxies:
            try:
                results.append(self.check_proxy(p["id"]))
            except Exception as e:
                logger.error("Error checking proxy %s: %s", p["id"], e)
        return results
