"""
Profile Repository: Manages profiles, MMO attributes, project grouping, and soft-delete.
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from src.infrastructure.database.connection import DEFAULT_DB_PATH, db_session


def _apply_cookie_import(payload: dict[str, Any]) -> None:
    """A (re)imported cookie replaces the captured browser session and carries its own expiry."""
    if "cookies_json" not in payload:
        return
    from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

    if "cookies_browser" not in payload:
        payload["cookies_browser"] = None
        payload.setdefault("cookies_synced_at", None)
    if "session_expires_at" not in payload:
        try:
            payload["session_expires_at"] = BrowserCookieInjector.session_expiry(payload["cookies_json"] or "")
        except Exception:
            payload["session_expires_at"] = None


class ProfileRepository:
    """Repository for managing the `profiles` table."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def create(self, data: dict[str, Any] | None = None, **kwargs: Any) -> int:
        payload = dict(data or {})
        payload.update(kwargs)
        if "uuid" not in payload:
            payload["uuid"] = str(uuid.uuid4())
        if "name" not in payload:
            payload["name"] = f"Profile_{payload['uuid'][:8]}"
        if "storage_dir" not in payload:
            payload["storage_dir"] = f"profiles/{payload['name']}"
        # Unknown until synced from TikTok (schema default 1 would claim "private").
        payload.setdefault("privacy", None)
        if "user_agent" not in payload:
            payload["user_agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0"

        # Alias mappings
        if "tiktok_id" in payload and "username_on_tiktok" not in payload:
            payload["username_on_tiktok"] = payload.pop("tiktok_id")
        elif "tiktok_id" in payload:
            payload.pop("tiktok_id")

        if "cookie" in payload and "cookies_json" not in payload:
            payload["cookies_json"] = payload.pop("cookie")
        elif "cookie" in payload:
            payload.pop("cookie")
        _apply_cookie_import(payload)

        if "qg" in payload and "country" not in payload:
            payload["country"] = payload.pop("qg")
        elif "qg" in payload:
            payload.pop("qg")

        if "note" in payload and "notes" not in payload:
            payload["notes"] = payload.pop("note")
        elif "note" in payload:
            payload.pop("note")

        with db_session(self.db_path) as conn:
            col_rows = conn.execute("PRAGMA table_info(profiles);").fetchall()
            valid_cols = {r["name"] for r in col_rows}
            clean_payload = {k: v for k, v in payload.items() if k in valid_cols}

            cols = list(clean_payload.keys())
            placeholders = ", ".join("?" for _ in cols)
            sql = f"INSERT INTO profiles ({', '.join(cols)}) VALUES ({placeholders});"
            cur = conn.execute(sql, tuple(clean_payload.values()))
            assert cur.lastrowid is not None  # always set after a successful INSERT
            return int(cur.lastrowid)

    def get_by_id(self, profile_id: int) -> dict[str, Any] | None:
        with db_session(self.db_path, write=False) as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id = ?;", (profile_id,)).fetchone()
            return dict(row) if row else None

    def get_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        with db_session(self.db_path, write=False) as conn:
            row = conn.execute("SELECT * FROM profiles WHERE uuid = ?;", (uuid,)).fetchone()
            return dict(row) if row else None

    def list_active(
        self,
        project_id: int | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Returns non-trashed profiles, optionally filtered by project_id."""
        with db_session(self.db_path, write=False) as conn:
            if project_id is not None:
                query = """
                SELECT * FROM profiles
                WHERE is_trashed = 0 AND project_id = ?
                ORDER BY id DESC LIMIT ? OFFSET ?;
                """
                rows = conn.execute(query, (project_id, limit, offset)).fetchall()
            else:
                query = """
                SELECT * FROM profiles
                WHERE is_trashed = 0
                ORDER BY id DESC LIMIT ? OFFSET ?;
                """
                rows = conn.execute(query, (limit, offset)).fetchall()
            return [dict(r) for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        """Returns all non-trashed profiles."""
        return self.list_active(limit=100000)

    def bulk_assign_project(self, profile_ids: list[int], project_id: int | None) -> int:
        """Atomically moves a list of profiles to a target project in a single transaction."""
        if not profile_ids:
            return 0

        placeholders = ", ".join("?" for _ in profile_ids)
        sql = f"UPDATE profiles SET project_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders});"
        params = [project_id] + profile_ids

        with db_session(self.db_path) as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount

    def bulk_assign_proxy(self, profile_ids: list[int], proxy_id: int | None) -> int:
        """Atomically assigns a proxy to a list of profiles in a single transaction."""
        if not profile_ids:
            return 0

        placeholders = ", ".join("?" for _ in profile_ids)
        # Assigning a real proxy ends deliberate direct mode, so losing that proxy later is blocked again.
        direct_sql = ", direct_connection = 0" if proxy_id is not None else ""
        sql = (
            f"UPDATE profiles SET proxy_id = ?{direct_sql}, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id IN ({placeholders});"
        )
        params = [proxy_id] + profile_ids

        with db_session(self.db_path) as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount

    def bulk_update_status(self, profile_ids: list[int], status: str) -> int:
        """Atomically updates status for a list of profiles."""
        if not profile_ids:
            return 0

        placeholders = ", ".join("?" for _ in profile_ids)
        sql = f"UPDATE profiles SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders});"
        params = [status] + profile_ids

        with db_session(self.db_path) as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount

    def set_direct_connection(self, profile_ids: list[int]) -> int:
        """User-confirmed: run these profiles WITHOUT proxy/VPN, from the machine's own IP."""
        return self.bulk_update_fields(
            profile_ids, {"proxy_id": None, "vpn_config": None, "direct_connection": 1}
        )

    def bulk_update_fields(self, profile_ids: list[int], fields: dict[str, Any]) -> int:
        """Atomically updates arbitrary fields for a list of profile IDs."""
        if not profile_ids or not fields:
            return 0
        payload = dict(fields)
        if "direct_connection" not in payload and (payload.get("proxy_id") or payload.get("vpn_config")):
            payload["direct_connection"] = 0  # a proxy/VPN was assigned: direct mode ends
        if "qg" in payload and "country" not in payload:
            payload["country"] = payload.pop("qg")
        elif "qg" in payload:
            payload.pop("qg")

        if "note" in payload and "notes" not in payload:
            payload["notes"] = payload.pop("note")
        elif "note" in payload:
            payload.pop("note")

        with db_session(self.db_path) as conn:
            col_rows = conn.execute("PRAGMA table_info(profiles);").fetchall()
            valid_cols = {r["name"] for r in col_rows}
            clean_payload = {k: v for k, v in payload.items() if k in valid_cols}
            if not clean_payload:
                return 0

            set_clauses = [f"{k} = ?" for k in clean_payload.keys()]
            placeholders = ", ".join("?" for _ in profile_ids)
            sql = f"UPDATE profiles SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders});"
            params = list(clean_payload.values()) + profile_ids
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount

    def soft_delete(self, profile_id: int) -> bool:
        """Soft-deletes a profile by marking is_trashed = 1."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE profiles SET is_trashed = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (profile_id,),
            )
            return cur.rowcount > 0

    def restore(self, profile_id: int) -> bool:
        """Restores a soft-deleted profile."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE profiles SET is_trashed = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (profile_id,),
            )
            return cur.rowcount > 0

    def update(self, profile_id: int, data: dict[str, Any] | None = None, **fields: Any) -> bool:
        """Updates profile columns via dictionary and/or keyword arguments."""
        payload = dict(data or {})
        payload.update(fields)
        if not payload:
            return False

        if "qg" in payload and "country" not in payload:
            payload["country"] = payload.pop("qg")
        elif "qg" in payload:
            payload.pop("qg")

        if "note" in payload and "notes" not in payload:
            payload["notes"] = payload.pop("note")
        elif "note" in payload:
            payload.pop("note")
        if "cookie" in payload and "cookies_json" not in payload:
            payload["cookies_json"] = payload.pop("cookie")
        _apply_cookie_import(payload)
        if "direct_connection" not in payload and (payload.get("proxy_id") or payload.get("vpn_config")):
            payload["direct_connection"] = 0  # a proxy/VPN was assigned: direct mode ends

        with db_session(self.db_path) as conn:
            col_rows = conn.execute("PRAGMA table_info(profiles);").fetchall()
            valid_cols = {r["name"] for r in col_rows}
            clean_payload = {k: v for k, v in payload.items() if k in valid_cols}
            if not clean_payload:
                return False

            cols = [f"{k} = ?" for k in clean_payload.keys()]
            sql = f"UPDATE profiles SET {', '.join(cols)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?;"
            params = list(clean_payload.values()) + [profile_id]
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount > 0
