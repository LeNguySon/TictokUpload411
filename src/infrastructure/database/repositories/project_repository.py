"""
Project Repository: Project / Campaign Grouping Management.
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.infrastructure.database.connection import DEFAULT_DB_PATH, db_session


class ProjectRepository:
    """CRUD and aggregation queries for the `projects` table."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def create(self, name: str, description: str | None = None, color: str = "#0078D4") -> int:
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, description, color) VALUES (?, ?, ?);",
                (name, description, color),
            )
            return int(cur.lastrowid)

    def get_by_id(self, project_id: int) -> dict[str, Any] | None:
        with db_session(self.db_path, write=False) as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
            return dict(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        with db_session(self.db_path, write=False) as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY id ASC;").fetchall()
            return [dict(r) for r in rows]

    def update(
        self,
        project_id: int,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> bool:
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if color is not None:
            updates.append("color = ?")
            params.append(color)

        if not updates:
            return False

        params.append(project_id)
        with db_session(self.db_path) as conn:
            cur = conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?;", tuple(params))
            return cur.rowcount > 0

    def delete(self, project_id: int) -> bool:
        """Deletes a project safely. Foreign keys set project_id = NULL on profiles."""
        with db_session(self.db_path) as conn:
            cur = conn.execute("DELETE FROM projects WHERE id = ?;", (project_id,))
            return cur.rowcount > 0

    def get_aggregates(self) -> list[dict[str, Any]]:
        """Returns campaign aggregates (total profiles, live count, views, earned) per project."""
        query = """
        SELECT
            p.id AS project_id,
            p.name AS project_name,
            p.color AS project_color,
            COUNT(pr.id) AS total_profiles,
            SUM(CASE WHEN pr.status = 'LIVE' THEN 1 ELSE 0 END) AS live_count,
            SUM(CASE WHEN pr.status = 'DIE' THEN 1 ELSE 0 END) AS die_count,
            COALESCE(SUM(pr.views_month), 0) AS total_views_30d,
            COALESCE(SUM(pr.money_earned), 0.0) AS total_earned_usd,
            COALESCE(SUM(pr.balance), 0.0) AS total_balance_usd
        FROM projects p
        LEFT JOIN profiles pr ON p.id = pr.project_id AND pr.is_trashed = 0
        GROUP BY p.id
        ORDER BY p.id ASC;
        """
        with db_session(self.db_path, write=False) as conn:
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]
