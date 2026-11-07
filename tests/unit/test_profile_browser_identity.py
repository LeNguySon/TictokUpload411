"""Every request made for a profile must present the SAME browser as the profile's real browser (live 2026-11-07:
the Orbita browser of profile 78 is Chrome/139 on Windows, languages vi-VN; canvas/WebGL stable across launches).

The app's own HTTP paths did not: Creator API = TLS Chrome 120 + Accept-Language en-US; curl_cffi also added
Sec-Ch-Ua v136 and Sec-Ch-Ua-Platform "macOS" to a Windows User-Agent; avatar download = Chrome 123; DOM fetch =
Chrome/152 + en-US.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.tiktok import browser_identity as bi

UA139 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
FP = {
    "navigator": {"user_agent": UA139, "platform": "Win32", "languages": ["vi-VN", "vi", "en-US", "en"]},
    "webgl": {}, "screen": {},
}
PROFILE = {"id": 78, "uuid": "u-78", "user_agent": UA139, "fingerprint_json": json.dumps(FP)}


@pytest.mark.parametrize(
    "ua, target",
    [(UA139, "chrome136"), (UA139.replace("139", "152"), "chrome152"), (UA139.replace("139", "120"), "chrome120"),
     (UA139.replace("139", "98"), "chrome99"), ("", bi.DEFAULT_IMPERSONATE)],
)
def test_tls_target_is_the_closest_chrome_not_newer_than_the_user_agent(ua, target):
    assert bi.impersonate_target(ua) == target


def test_headers_match_the_profile_browser():
    headers, target = bi.request_identity(PROFILE)
    assert headers["User-Agent"] == UA139
    assert headers["Accept-Language"] == "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
    assert '"Google Chrome";v="139"' in headers["sec-ch-ua"] and '"Chromium";v="139"' in headers["sec-ch-ua"]
    assert headers["sec-ch-ua-platform"] == '"Windows"' and headers["sec-ch-ua-mobile"] == "?0"
    assert target == "chrome136"


def test_profile_without_stored_languages_still_gets_consistent_headers():
    headers, _ = bi.request_identity({"id": 1, "uuid": "x"})  # fingerprint derived from the uuid
    assert "Chrome/" in headers["User-Agent"] and headers["Accept-Language"].startswith("en-US")
    major = bi.chrome_major(headers["User-Agent"])
    assert f'v="{major}"' in headers["sec-ch-ua"]


def _client(tmp_path: Path):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient

    db = tmp_path / "app.db"
    run_all_migrations(db)
    pid = ProfileRepository(db).create(
        {"name": "p", "uuid": "u-78", "fingerprint_json": json.dumps(FP), "direct_connection": 1,
         "cookies_json": "sessionid=x"}
    )
    return GoLoginTikTokClient(db_path=db), pid, db


def test_creator_api_requests_use_the_profile_identity(tmp_path):
    client, pid, _ = _client(tmp_path)
    resp = MagicMock(status_code=200)
    resp.json.return_value = {}
    with patch("curl_cffi.requests.request", return_value=resp) as req:
        client.request_api(pid, "https://www.tiktok.com/api/user/detail/")
    kw = req.call_args.kwargs
    assert kw["impersonate"] == "chrome136"
    assert kw["headers"]["User-Agent"] == UA139
    assert kw["headers"]["sec-ch-ua-platform"] == '"Windows"'
    assert kw["headers"]["Accept-Language"].startswith("vi-VN")


def test_avatar_download_uses_the_profile_identity(tmp_path):
    from src.infrastructure.tiktok import avatar_cache_service as av

    _, pid, db = _client(tmp_path)
    resp = MagicMock(status_code=200, content=b"img")
    with patch("curl_cffi.requests.get", return_value=resp) as get:
        av._http_get("https://p16.tiktokcdn.com/a.jpg", None, 5, profile=PROFILE)
    kw = get.call_args.kwargs
    assert kw["impersonate"] == "chrome136" and kw["headers"]["User-Agent"] == UA139


def test_dom_fetch_uses_the_profile_identity(tmp_path):
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService

    _, pid, db = _client(tmp_path)
    repo = ProfileRepository(db)
    svc = PassiveTikTokSyncService(repo, db_path=db)
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"<html></html>"

    def fake_open(req, timeout=None):
        seen.update(dict(req.header_items()))
        return _Resp()

    with patch("urllib.request.OpenerDirector.open", side_effect=fake_open):
        svc._fetch_page_via_proxy(pid, "https://www.tiktok.com/@x")
    assert seen.get("User-agent") == UA139
    assert seen.get("Accept-language", "").startswith("vi-VN")
