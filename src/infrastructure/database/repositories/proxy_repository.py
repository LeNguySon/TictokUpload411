"""
Proxy Repository & Smart Format Parser (Bulk Import & Health Tracking).
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.infrastructure.database.connection import DEFAULT_DB_PATH, db_session


def parse_proxy_line(raw_line: str) -> tuple[str, int, str | None, str | None, str, str | None] | None:
    """Smart Format Parser: Auto-detects 5 common proxy formats:
    1. host:port:username:password
    2. username:password@host:port
    3. protocol://username:password@host:port
    4. host:port
    5. host:port:username:password:change_ip_url
    Returns: (host, port, username, password, protocol, change_ip_url)
    """
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None

    # Detect change_ip_url at end if present
    change_ip_url = None
    match_url = re.search(r":(https?://\S+)$", line)
    if match_url:
        change_ip_url = match_url.group(1)
        line = line[: match_url.start()]

    protocol = "http"
    if "://" in line:
        parts = line.split("://", 1)
        protocol = parts[0].lower()
        line = parts[1]

    # Format 2 & 3: user:pass@host:port
    if "@" in line:
        auth_part, host_part = line.split("@", 1)
        user_pass = auth_part.split(":", 1)
        username = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else None

        host_port = host_part.split(":")
        host = host_port[0]
        try:
            port = int(host_port[1])
            return (host, port, username, password, protocol, change_ip_url)
        except (IndexError, ValueError):
            return None

    # Colon-separated formats: host:port[:user:pass]
    tokens = line.split(":")
    if len(tokens) == 2:
        # host:port
        host = tokens[0]
        try:
            port = int(tokens[1])
            return (host, port, None, None, protocol, change_ip_url)
        except ValueError:
            return None
    elif len(tokens) >= 4:
        host = tokens[0]
        try:
            port = int(tokens[1])
        except ValueError:
            return None
        username = tokens[2]
        password = tokens[3]
        return (host, port, username, password, protocol, change_ip_url)

    return None


class ProxyRepository:
    """Repository for managing the `proxies` table."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def create(
        self,
        host: str,
        port: int,
        protocol: str = "http",
        username: str | None = None,
        password: str | None = None,
        proxy_type: str = "static",
        change_ip_url: str | None = None,
    ) -> int:
        """Inserts a single proxy record into the database."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO proxies (
                    host, port, username, password, protocol, proxy_type, change_ip_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host, port, username) DO UPDATE SET
                    password = excluded.password,
                    protocol = excluded.protocol,
                    change_ip_url = excluded.change_ip_url;
                """,
                (host, port, username, password, protocol, proxy_type, change_ip_url),
            )
            return int(cur.lastrowid or 0)

    def bulk_import(self, raw_lines: list[str]) -> int:
        """Parses and imports a batch of proxy strings. Unique proxies counted."""
        seen_keys: set[tuple[str, int, str | None]] = set()
        with db_session(self.db_path) as conn:
            for line in raw_lines:
                parsed = parse_proxy_line(line)
                if not parsed:
                    continue

                host, port, username, password, protocol, change_ip_url = parsed
                proxy_type = "rotating" if change_ip_url else "static"
                key = (host, port, username)

                conn.execute(
                    """
                    INSERT INTO proxies (
                        host, port, username, password, protocol, proxy_type, change_ip_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(host, port, username) DO UPDATE SET
                        password = excluded.password,
                        protocol = excluded.protocol,
                        change_ip_url = excluded.change_ip_url;
                    """,
                    (host, port, username, password, protocol, proxy_type, change_ip_url),
                )
                seen_keys.add(key)

        return len(seen_keys)

    def get_by_id(self, proxy_id: int) -> dict[str, Any] | None:
        with db_session(self.db_path, write=False) as conn:
            row = conn.execute("SELECT * FROM proxies WHERE id = ?;", (proxy_id,)).fetchone()
            return dict(row) if row else None

    def list_all(self, status: str | None = None) -> list[dict[str, Any]]:
        with db_session(self.db_path, write=False) as conn:
            if status:
                rows = conn.execute("SELECT * FROM proxies WHERE status = ? ORDER BY id ASC;", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM proxies ORDER BY id ASC;").fetchall()
            return [dict(r) for r in rows]

    def mark_ip_leak(self, proxy_id: int, error_msg: str) -> bool:
        """Marks a proxy as dangerous due to local machine IP leak."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE proxies
                SET status = 'leak_detected', error_message = ?, latency_ms = -1, last_checked_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (error_msg, proxy_id),
            )
            return cur.rowcount > 0

    def update_health(
        self,
        proxy_id: int,
        status: str,
        latency_ms: int,
        public_ip: str | None = None,
        country_code: str | None = None,
        city: str | None = None,
        timezone: str | None = None,
        isp: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE proxies
                SET status = ?, latency_ms = ?, public_ip = ?, country_code = ?,
                    city = ?, timezone = ?, isp = ?, error_message = ?, last_checked_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (status, latency_ms, public_ip, country_code, city, timezone, isp, error_message, proxy_id),
            )
            return cur.rowcount > 0

    def update(self, proxy_id: int, **kwargs: Any) -> bool:
        """Dynamically updates proxy attributes."""
        if not kwargs:
            return False
        cols = []
        vals = []
        for k, v in kwargs.items():
            cols.append(f"{k} = ?")
            vals.append(v)
        vals.append(proxy_id)
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                f"UPDATE proxies SET {', '.join(cols)} WHERE id = ?;",
                tuple(vals),
            )
            return cur.rowcount > 0

    def delete(self, proxy_id: int) -> bool:
        """Deletes a single proxy record by ID."""
        with db_session(self.db_path) as conn:
            cur = conn.execute("DELETE FROM proxies WHERE id = ?;", (proxy_id,))
            return cur.rowcount > 0

    def delete_many(self, proxy_ids: list[int]) -> int:
        """Deletes multiple proxy records by their IDs."""
        if not proxy_ids:
            return 0
        placeholders = ", ".join("?" for _ in proxy_ids)
        with db_session(self.db_path) as conn:
            cur = conn.execute(f"DELETE FROM proxies WHERE id IN ({placeholders});", tuple(proxy_ids))
            return cur.rowcount

    def delete_dead(self) -> int:
        with db_session(self.db_path) as conn:
            cur = conn.execute("DELETE FROM proxies WHERE status IN ('dead', 'leak_detected');")
            return cur.rowcount
