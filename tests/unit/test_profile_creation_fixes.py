"""Profile creation (single + bulk), checked live on a copy of the real DB with the real daemon on 2026-11-07:

1. a cookie without a TikTok session (msToken only = not logged in) gave status LIVE;
2. importing the same account twice created two profiles (two browsers, two fingerprints, one TikTok account);
3. a failure AFTER the daemon created the profile fell back to a second, local profile: orphan daemon profile;
4. with the daemon down, every row of a bulk import tried to start it again (up to ~6 s per row).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.cookie_injector import BrowserCookieInjector
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

JSON_SESSION = '[{"name": "sessionid", "value": "abc", "domain": ".tiktok.com"}]'


@pytest.mark.parametrize(
    "cookie, expected",
    [
        ("sessionid=abc; tt_csrf_token=x", True),
        ("sid_tt=abc", True),
        (JSON_SESSION, True),
        ("msToken=only; tt_csrf_token=x", False),
        ('[{"name": "msToken", "value": "x"}]', False),
        ("", False),
        (None, False),
    ],
)
def test_has_session_cookie(cookie, expected):
    assert BrowserCookieInjector.has_session_cookie(cookie) is expected


@pytest.fixture
def repos(tmp_path: Path, monkeypatch):
    db = tmp_path / "app.db"
    run_all_migrations(db)
    monkeypatch.setattr(
        "src.infrastructure.browser.orbita_launcher.OrbitaLauncher.resolve_profile_dir",
        classmethod(lambda cls, p: (tmp_path / "profiles" / str(p["uuid"] if isinstance(p, dict) else p))),
    )
    return {"profile_repo": ProfileRepository(db), "project_repo": ProjectRepository(db), "proxy_repo": ProxyRepository(db)}


@pytest.fixture
def daemon():
    """A healthy fake daemon: GoLogin.create returns a new uuid each time."""
    import itertools

    counter = itertools.count(1)
    with patch("sammonny.gologin.gologin.GoLogin.create", side_effect=lambda payload: f"uuid-{next(counter)}") as create, \
            patch("sammonny.gologin.gologin.GoLogin.delete") as delete, \
            patch("src.application.services.gologin_sync_service._daemon_fingerprint", return_value=None), \
            patch("src.infrastructure.browser.sammonny_daemon_manager.SamMonnyDaemonSupervisor.ensure_daemon_running",
                  return_value=True) as ensure:
        yield {"create": create, "delete": delete, "ensure": ensure}


def _sync(repos):
    from src.application.services.gologin_sync_service import GoLoginSyncService

    return GoLoginSyncService(**repos)


def test_daemon_profile_without_session_cookie_is_not_live(repos, daemon):
    svc = _sync(repos)
    live = svc.create_real_gologin_profile(name="a", cookie="sessionid=abc")
    not_logged_in = svc.create_real_gologin_profile(name="b", cookie="msToken=only")
    assert repos["profile_repo"].get_by_id(live)["status"] == "LIVE"
    assert repos["profile_repo"].get_by_id(not_logged_in)["status"] == "stopped"


def test_local_profile_without_session_cookie_is_not_live(repos):
    svc = _sync(repos)
    pid = svc.create_local_profile(name="c", cookie="msToken=only")
    row = repos["profile_repo"].get_by_id(pid)
    assert row["status"] == "stopped"
    assert Path(row["storage_dir"]).is_dir()
    assert row["fingerprint_json"]


def test_failure_after_daemon_create_deletes_the_daemon_profile(repos, daemon):
    svc = _sync(repos)
    with patch.object(repos["profile_repo"], "create", side_effect=RuntimeError("disk full")):
        with pytest.raises(RuntimeError):
            svc.create_real_gologin_profile(name="x", cookie="sessionid=abc")
    daemon["delete"].assert_called_once_with("uuid-1")


def test_single_create_does_not_leave_an_orphan_daemon_profile(repos, daemon):
    """create_profile falls back to a local profile; the daemon one created before the failure is removed."""
    from src.presentation.dialogs.add_profile_dialog import create_profile

    real_create = repos["profile_repo"].create
    calls = {"n": 0}

    def flaky(data=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return real_create(data, **kw)

    with patch.object(repos["profile_repo"], "create", side_effect=flaky):
        pid = create_profile(name="y", project_id=None, proxy_id=None, cookie="", token="", vault=MagicMock(), **repos)
    daemon["delete"].assert_called_once_with("uuid-1")
    assert repos["profile_repo"].get_by_id(pid)["uuid"] != "uuid-1"


def test_bulk_import_skips_accounts_already_present(repos, daemon):
    from src.presentation.dialogs.bulk_add_profile_dialog import import_profiles

    repos["profile_repo"].create({"name": "existing.acc", "username_on_tiktok": "@existing.acc"})
    rows = [
        {"user": "new.acc", "cookie": "sessionid=1"},
        {"user": "New.Acc", "cookie": "sessionid=1"},  # same account again in the same list
        {"user": "@existing.acc", "cookie": "sessionid=2"},  # already in the app
        {"user": "other.acc"},
    ]
    summary = import_profiles(rows, project_id=None, auto_inject=False, **repos)
    assert summary.created == 2
    assert summary.duplicate_rows == ["New.Acc", "@existing.acc"]
    names = sorted(p["name"] for p in repos["profile_repo"].list_all())
    assert names == ["existing.acc", "new.acc", "other.acc"]


def test_bulk_import_checks_the_daemon_once_and_goes_local_when_down(repos, daemon):
    from src.presentation.dialogs.bulk_add_profile_dialog import import_profiles

    daemon["ensure"].return_value = False
    rows = [{"user": f"acc{i}"} for i in range(4)]
    summary = import_profiles(rows, project_id=None, auto_inject=False, **repos)
    assert summary.created == 4
    assert daemon["ensure"].call_count == 1
    daemon["create"].assert_not_called()
    assert all(Path(p["storage_dir"]).is_dir() for p in repos["profile_repo"].list_all())
