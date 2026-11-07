"""
Failures that used to vanish in ``except Exception: pass`` must be reported to the user:
- bulk import counted a cookie as "loaded" even when seeding the profile's cookies failed;
- "Xoay IP" always announced success, even when the provider endpoint could not be reached.
"""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

LINE = "creator_x|pw_fake_1|sessionid=fake_sess_1; msToken=fake_tok|x@example.com|mp|rf|cid|mck"


@pytest.fixture
def repos(tmp_path):
    db = tmp_path / "silent.db"
    run_all_migrations(db)
    return ProfileRepository(db_path=db), ProjectRepository(db_path=db), ProxyRepository(db_path=db)


def _import_with_seed(qapp, repos, seed_side_effect):
    from src.presentation.dialogs import bulk_add_profile_dialog as mod

    profile_repo, project_repo, proxy_repo = repos
    dlg = mod.BulkAddProfileDialog(profile_repo=profile_repo, project_repo=project_repo, proxy_repo=proxy_repo)
    dlg.chk_auto_inject_cookie.setChecked(True)
    dlg.txt_input.setPlainText(LINE)
    with (
        patch("src.infrastructure.browser.cookie_injector.BrowserCookieInjector.inject_to_gologin", return_value=True),
        patch.object(mod.BrowserCookieInjector, "seed_profile_cookies", side_effect=seed_side_effect),
        patch.object(mod, "InfoBar") as info,
    ):
        dlg._on_import_all()
        assert drain_ui_tasks(timeout_s=15)  # the import runs off the GUI thread
    return info


def test_bulk_import_does_not_count_failed_cookie_seed(qapp, repos) -> None:
    info = _import_with_seed(qapp, repos, OSError("Cookies file locked"))

    success_text = info.success.call_args.kwargs["content"]
    assert "nạp cookie" not in success_text
    warnings = " ".join(str(c.kwargs.get("content", "")) for c in info.warning.call_args_list)
    assert "creator_x" in warnings  # the user is told which account has no cookies


def test_bulk_import_counts_successful_cookie_seed(qapp, repos) -> None:
    info = _import_with_seed(qapp, repos, None)

    assert "nạp cookie tự động đăng nhập cho 1 tài khoản" in info.success.call_args.kwargs["content"]


def test_rotate_ip_via_url_raises_on_unreachable_endpoint() -> None:
    from src.presentation.dialogs.proxy_dialog import rotate_ip_via_url

    with (
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")),
        pytest.raises(urllib.error.URLError),
    ):
        rotate_ip_via_url("https://provider.example/rotate?key=fake")


def test_trigger_rotate_ip_reports_failure_instead_of_success(qapp, repos) -> None:
    from src.presentation.dialogs import proxy_dialog as mod

    _, _, proxy_repo = repos
    dlg = mod.ProxyManagerDialog(proxy_repo=proxy_repo, proxy_service=MagicMock())
    with (
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")),
        patch.object(mod, "InfoBar") as info,
    ):
        dlg._trigger_rotate_ip("https://provider.example/rotate?key=fake")
        assert drain_ui_tasks()

    info.error.assert_called_once()
    info.success.assert_not_called()
    dlg.close()
