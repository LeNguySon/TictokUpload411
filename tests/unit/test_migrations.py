"""
Unit tests for 24-table SQLite Migration Runner & Foreign Key Enforcement.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from src.infrastructure.database.connection import db_session
from src.infrastructure.database.migrations.runner import get_database_tables, run_all_migrations


def test_migrations_create_all_tables():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_mig.db"

        # Run migrations
        run_all_migrations(db_path)

        # Assert key tables exist
        required_tables = {
            "projects",
            "proxies",
            "profiles",
            "profile_fonts",
            "activity_logs",
            "tiktok_sessions",
            "tiktok_queue",
            "affiliate_products",
            "statisticTable",
            "phoneParams",
            "violateVideos",
            "violateProfiles",
            "videoTables",
            "accountAppeals",
            "tiktok_report_observations",
            "video_registry",
        }

        existing_tables = set(get_database_tables(db_path))
        missing = required_tables - existing_tables
        assert not missing, f"Missing required database tables: {missing}"


def test_foreign_key_enforcement_on_profiles():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_fk.db"
        run_all_migrations(db_path)

        with db_session(db_path) as conn:
            # Inserting profile with non-existent project_id (e.g. 9999) must fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO profiles (uuid, name, storage_dir, user_agent, project_id)
                    VALUES ('test-uuid-1', 'Invalid Profile', '/storage', 'Mozilla/5.0', 9999);
                    """
                )


def test_profile_table_has_mmo_columns():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_cols.db"
        run_all_migrations(db_path)

        with db_session(db_path, write=False) as conn:
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(profiles);").fetchall()}

            # Check for the 28 columns required by the UI/UX spec
            mmo_cols = [
                "username_on_tiktok",
                "avatar_url",
                "avatar_path",
                "state_loggin_browser",
                "total_followers",
                "total_likes",
                "total_videos",
                "total_views",
                "views_month",
                "money_earned",
                "balance",
                "rpm",
                "country",
                "state_kyc",
                "notes",
                "date_reapply",
                "privacy",
                "vat",
                "auth_2fa",
            ]
            for col in mmo_cols:
                assert col in columns, f"Missing MMO column '{col}' in profiles table"
