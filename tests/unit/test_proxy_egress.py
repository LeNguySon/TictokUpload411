"""Proxy attached to profiles and the proxy used by every outbound request (deep audit 2026-11-06).

Defects reproduced here:
1. Official Direct Post upload: the SDK calls init_direct_post / upload_video_chunks WITHOUT proxy_url,
   so the video was uploaded from the host IP even when the profile had a proxy.
2. Upload browser session (hybrid / studio): no gate, a missing or leak-flagged proxy still started it.
3. fetch_creator_metrics went direct when the profile had no proxy.
4. Proxy credentials were written to the log (and the redaction filter had no URL-credentials rule).
5. Proxy URLs were built without URL-encoding the credentials (5 copies of the builder).
6. socks5:// lets the client resolve DNS locally (DNS leak); socks5h:// resolves through the proxy.
7. The health check read row["scheme"] (no such column): every SOCKS proxy was checked as HTTP.
8. The leak policy only knew LAN addresses, never the public IP, so a proxy exiting via the host
   IP was never flagged.
9. Parser: passwords with "@" or ":" were truncated; invalid ports / protocols accepted.
10. ProxyRepository.create returned 0 for an existing proxy (bulk-paste assigned proxy_id 0).
11. Upload session cookies: expires None reached Network.setCookies after the real-expiry change.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository, parse_proxy_line
from src.infrastructure.proxy.egress import (
    EgressBlocked,
    build_proxy_url,
    redact_proxy_url,
    resolve_profile_egress,
)

PROXY = {"id": 9, "host": "203.0.113.7", "port": 8000, "protocol": "http", "username": "u@x", "password": "p:a/s#s",
         "status": "alive"}


@pytest.fixture
def repos(tmp_path):
    db = tmp_path / "e.db"
    run_all_migrations(db)
    return ProfileRepository(db), ProxyRepository(db), db


# ------------------------------------------------------------------ central egress resolution
def test_build_proxy_url_encodes_credentials_and_uses_remote_dns_for_socks():
    assert build_proxy_url(PROXY) == "http://u%40x:p%3Aa%2Fs%23s@203.0.113.7:8000"
    socks = {**PROXY, "protocol": "socks5", "username": "a", "password": "b"}
    assert build_proxy_url(socks) == "socks5h://a:b@203.0.113.7:8000"
    assert build_proxy_url({"host": "h", "port": 1, "protocol": "http"}) == "http://h:1"
    assert build_proxy_url({"host": "", "port": 1}) is None


def test_redact_proxy_url_hides_credentials():
    assert redact_proxy_url("socks5h://user:secret@1.2.3.4:1080") == "socks5h://***@1.2.3.4:1080"
    assert redact_proxy_url(None) == "none"


@pytest.mark.parametrize(
    ("profile", "proxy", "expected"),
    [
        ({"id": 1}, PROXY, "http://u%40x:p%3Aa%2Fs%23s@203.0.113.7:8000"),
        ({"id": 1, "direct_connection": 1}, None, None),  # deliberate host IP
    ],
)
def test_resolve_profile_egress_allowed(profile, proxy, expected):
    assert resolve_profile_egress(profile, proxy) == expected


@pytest.mark.parametrize(
    ("profile", "proxy"),
    [
        ({"id": 1}, None),  # no proxy, no opt-in
        ({"id": 1, "direct_connection": 1}, {**PROXY, "status": "leak_detected"}),  # leak beats opt-in
        ({"id": 1}, {**PROXY, "host": ""}),  # broken proxy row
        ({"id": 1, "vpn_config": "[Interface]"}, None),  # WireGuard is browser-only
    ],
)
def test_resolve_profile_egress_blocked(profile, proxy):
    with pytest.raises(EgressBlocked):
        resolve_profile_egress(profile, proxy)


# ------------------------------------------------------------------ 1. official upload uses the proxy
def test_direct_post_client_injects_bound_proxy():
    from src.infrastructure.tiktok.sammonny_adapter import ProxyBoundDirectPostClient

    client = ProxyBoundDirectPostClient()
    seen = {}

    def fake_init(self, access_token, title, video_size_bytes, privacy_level="SELF_ONLY", disable_duet=False,
                  disable_comment=False, disable_stitch=False, cover_timestamp_ms=1000, proxy_url=None):
        seen["init"] = proxy_url
        return {"publish_id": "p", "upload_url": "u", "chunk_size": 1}

    def fake_chunks(self, upload_url, video_bytes, chunk_size, progress_callback=None, cancel_token=None,
                    proxy_url=None):
        seen["chunks"] = proxy_url
        return len(video_bytes)

    from sammonny.platforms.tiktok import TikTokDirectPostClient

    with patch.object(TikTokDirectPostClient, "init_direct_post", fake_init), patch.object(
        TikTokDirectPostClient, "upload_video_chunks", fake_chunks
    ):
        with client.bound("socks5h://a:b@1.2.3.4:1080"):
            client.init_direct_post(access_token="t", title="x", video_size_bytes=1)
            client.upload_video_chunks(upload_url="u", video_bytes=b"x", chunk_size=1)
        client.init_direct_post(access_token="t", title="x", video_size_bytes=1)
    assert seen["chunks"] == "socks5h://a:b@1.2.3.4:1080"
    assert seen["init"] is None  # outside the binding nothing is injected


def test_upload_video_binds_profile_proxy_and_refuses_unproxied(repos, tmp_path):
    from src.infrastructure.tiktok.sammonny_adapter import ProxyBoundDirectPostClient, SamMonnyTikTokAdapter

    profile_repo, proxy_repo, db = repos
    px = proxy_repo.import_line("socks5://a:b@198.51.100.4:1080")
    good = profile_repo.create({"name": "G", "uuid": "uuid-egress-1", "proxy_id": px})
    bare = profile_repo.create({"name": "B", "uuid": "uuid-egress-2"})
    client = ProxyBoundDirectPostClient()
    adapter = SamMonnyTikTokAdapter(vault=MagicMock(), direct_client=client, db_path=db,
                                    profile_repo=profile_repo, proxy_repo=proxy_repo)
    seen = []
    adapter.publisher = MagicMock()
    adapter.publisher.upload.side_effect = lambda **kw: seen.append(client.current_proxy()) or MagicMock(success=True)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 10)
    adapter.upload_video(profile_id=good, video_path=video, title="t")
    assert seen == ["socks5h://a:b@198.51.100.4:1080"]
    with pytest.raises(EgressBlocked):
        adapter.upload_video(profile_id=bare, video_path=video, title="t")
    assert len(seen) == 1  # nothing was sent for the unproxied profile


# ------------------------------------------------------------------ 2. upload browser session gate
def test_upload_session_refuses_missing_or_leaking_proxy(repos):
    from src.infrastructure.tiktok.sammonny_adapter import _default_session_factory

    profile_repo, proxy_repo, db = repos
    bare = profile_repo.create({"name": "B", "uuid": "uuid-sess-1"})
    leak_px = proxy_repo.import_line("1.2.3.4:80:u:p")
    proxy_repo.mark_ip_leak(leak_px, error_msg="leak")
    leaking = profile_repo.create({"name": "L", "uuid": "uuid-sess-2", "proxy_id": leak_px})
    with patch("src.infrastructure.tiktok.sammonny_adapter.AntidetectEngine") as engine:
        for pid in (bare, leaking):
            with pytest.raises(EgressBlocked):
                _default_session_factory(pid, db_path=db)
    engine.assert_not_called()


def test_upload_session_never_logs_proxy_credentials(repos, caplog):
    from src.infrastructure.tiktok.sammonny_adapter import _default_session_factory

    profile_repo, proxy_repo, db = repos
    px = proxy_repo.import_line("1.2.3.4:8080:alice:TopSecret99")
    pid = profile_repo.create({"name": "S", "uuid": "uuid-sess-3", "proxy_id": px})
    caplog.set_level(logging.DEBUG)
    with patch("src.infrastructure.tiktok.sammonny_adapter.AntidetectEngine"), patch(
        "src.infrastructure.browser.orbita_launcher.OrbitaLauncher.sync_daemon_profile_proxy"
    ):
        session = _default_session_factory(pid, db_path=db)
    assert "TopSecret99" not in caplog.text
    assert session.proxy_url == "http://alice:TopSecret99@1.2.3.4:8080"


def test_log_redaction_masks_url_credentials():
    from src.infrastructure.logging.redaction_logger import RedactionFilter

    out = RedactionFilter.redact("proxy socks5h://alice:TopSecret99@1.2.3.4:1080 ok")
    assert "TopSecret99" not in out and "1.2.3.4:1080" in out


# ------------------------------------------------------------------ 3. creator metrics gate
def test_creator_metrics_refuse_unproxied_profile(repos):
    from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter

    profile_repo, proxy_repo, db = repos
    pid = profile_repo.create({"name": "B", "uuid": "uuid-metrics-1"})
    direct_client = MagicMock()
    adapter = SamMonnyTikTokAdapter(vault=MagicMock(), direct_client=direct_client, db_path=db,
                                    profile_repo=profile_repo, proxy_repo=proxy_repo)
    with patch.object(adapter, "_sync_vault_token", return_value="tok"), pytest.raises(EgressBlocked):
        adapter.fetch_creator_metrics(pid)
    direct_client.query_creator_info.assert_not_called()


# ------------------------------------------------------------------ 7 + 8. health check & leak policy
def test_health_check_uses_the_proxy_protocol(repos):
    from src.application.services.proxy_service import ProxyService

    _, proxy_repo, _ = repos
    pid = proxy_repo.import_line("socks5://a:b@198.51.100.4:1080")
    item = ProxyService(proxy_repo, leak_policy=MagicMock())._to_proxy_item(proxy_repo.get_by_id(pid))
    assert item.mode == "socks5"


def test_leak_policy_knows_the_public_ip():
    from src.domain.policies.network_leak_policy import NetworkLeakPolicy

    with patch(
        "src.domain.policies.network_leak_policy.discover_public_ip", return_value="198.51.100.200"
    ) as lookup:
        policy = NetworkLeakPolicy()
        lookup.assert_not_called()  # never at construction (window start-up)
        assert policy.evaluate("198.51.100.200").leak_detected  # proxy exits through the host's public IP
        assert not policy.evaluate("203.0.113.9").leak_detected
    assert lookup.call_count == 1  # cached per policy


# ------------------------------------------------------------------ 9 + 10. parser and ids
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("user:p@ss@1.2.3.4:8080", ("1.2.3.4", 8080, "user", "p@ss", "http", None)),
        ("1.2.3.4:8080:user:pa:ss", ("1.2.3.4", 8080, "user", "pa:ss", "http", None)),
        ("SOCKS5://u:p@1.2.3.4:1080", ("1.2.3.4", 1080, "u", "p", "socks5", None)),
        ("socks5h://u:p@1.2.3.4:1080", ("1.2.3.4", 1080, "u", "p", "socks5", None)),
    ],
)
def test_parser_keeps_special_characters(line, expected):
    assert parse_proxy_line(line) == expected


@pytest.mark.parametrize("line", ["1.2.3.4:0", "1.2.3.4:70000", "sock5://1.2.3.4:80", "ftp://1.2.3.4:21"])
def test_parser_rejects_invalid(line):
    assert parse_proxy_line(line) is None


def test_create_returns_the_real_id_for_an_existing_proxy(repos):
    _, proxy_repo, _ = repos
    first = proxy_repo.create(host="1.1.1.1", port=80, username="u", password="p")
    proxy_repo.create(host="2.2.2.2", port=80, username="u", password="p")
    assert proxy_repo.create(host="1.1.1.1", port=80, username="u", password="p2") == first


# ------------------------------------------------------------------ 11. upload session cookie expiry
def test_lazy_session_cookies_have_numeric_expiry_and_skip_expired():
    import json
    import time

    from src.infrastructure.tiktok.sammonny_adapter import LazyActiveSession

    raw = json.dumps([
        {"name": "sessionid", "value": "s", "domain": ".tiktok.com", "expirationDate": time.time() + 99},
        {"name": "dead", "value": "d", "domain": ".tiktok.com", "expirationDate": time.time() - 99},
    ])
    session = MagicMock()
    session._cdp = None
    lazy = LazyActiveSession(session, cookie_raw="sessionid=abc; ttwid=t")
    lazy._ensure_active()
    sent = session.cdp.send.call_args_list[-1].args[1]["cookies"]
    assert all(isinstance(c["expires"], (int, float)) for c in sent)

    session2 = MagicMock()
    session2._cdp = None
    LazyActiveSession(session2, cookie_raw=raw)._ensure_active()
    names = [c["name"] for c in session2.cdp.send.call_args_list[-1].args[1]["cookies"]]
    assert names == ["sessionid"]


def test_every_proxied_sdk_method_exists_and_accepts_proxy_url():
    """Guards against SDK drift: a renamed method would silently go direct again."""
    import inspect

    from sammonny.platforms.tiktok import TikTokDirectPostClient
    from src.infrastructure.tiktok.sammonny_adapter import ProxyBoundDirectPostClient

    publisher_calls = set(
        __import__("re").findall(r"direct_client\.(\w+)\(", inspect.getsource(__import__("sammonny.platforms.tiktok").platforms.tiktok))
    )
    for name in ProxyBoundDirectPostClient._PROXIED_METHODS:
        assert "proxy_url" in inspect.signature(getattr(TikTokDirectPostClient, name)).parameters, name
    assert publisher_calls <= set(ProxyBoundDirectPostClient._PROXIED_METHODS), publisher_calls


# ------------------------------------------------------------------ other request clients
def _client(db):
    from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient

    return GoLoginTikTokClient(db_path=db)


def test_request_api_refuses_leak_flagged_proxy(repos):
    profile_repo, proxy_repo, db = repos
    px = proxy_repo.import_line("1.2.3.4:80:u:p")
    proxy_repo.mark_ip_leak(px, error_msg="leak")
    pid = profile_repo.create({"name": "L", "uuid": "uuid-req-1", "proxy_id": px})
    with patch("curl_cffi.requests.request") as req, pytest.raises(EgressBlocked):
        _client(db).request_api(pid, "https://www.tiktok.com/api/x")
    req.assert_not_called()


def test_request_api_sends_encoded_credentials_and_remote_dns(repos):
    profile_repo, proxy_repo, db = repos
    px = proxy_repo.import_line("socks5://us@r:p@ss@1.2.3.4:1080")
    pid = profile_repo.create({"name": "S", "uuid": "uuid-req-2", "proxy_id": px})
    with patch("curl_cffi.requests.request") as req:
        req.return_value.json.return_value = {}
        _client(db).request_api(pid, "https://www.tiktok.com/api/x")
    assert req.call_args.kwargs["proxies"]["https"] == "socks5h://us%40r:p%40ss@1.2.3.4:1080"


def test_moderation_request_without_profile_never_goes_direct(tmp_path):
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    svc = TikTokModerationService(db_path=tmp_path / "m.db")
    with patch("curl_cffi.requests.request") as req:
        result = svc._request_tiktok_api("https://www.tiktok.com/api/x", "sessionid=a", "UA", proxy_dict=None)
    req.assert_not_called()
    assert result.get("error")


def test_dom_fetch_never_falls_back_for_socks_and_honours_direct_opt_in(repos):
    from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService

    profile_repo, proxy_repo, db = repos
    svc = PassiveTikTokSyncService(profile_repo, proxy_repo)
    socks_px = proxy_repo.import_line("socks5://a:b@1.2.3.4:1080")
    socks_pid = profile_repo.create({"name": "S", "uuid": "uuid-dom-1", "proxy_id": socks_px})
    direct_pid = profile_repo.create({"name": "D", "uuid": "uuid-dom-2", "direct_connection": 1})
    with patch("urllib.request.OpenerDirector.open") as opened:
        assert svc._fetch_page_via_proxy(socks_pid, "https://www.tiktok.com/@x") == ""
        opened.assert_not_called()  # urllib cannot tunnel SOCKS: refused, not sent directly
        opened.return_value.__enter__.return_value.read.return_value = b"<html>ok</html>"
        assert svc._fetch_page_via_proxy(direct_pid, "https://www.tiktok.com/@x") == "<html>ok</html>"
