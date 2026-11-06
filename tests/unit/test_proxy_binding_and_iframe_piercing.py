"""Unit tests for proxy binding synchronization and Headless Studio iframe piercing.
Following ECC TDD (Test-Driven Development) methodology.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


def test_proxy_url_formatter_with_auth() -> None:
    """Tests formatting proxy dictionary with credentials into standard URI."""
    from src.infrastructure.tiktok.sammonny_adapter import format_proxy_url

    proxy_data = {
        "host": "118.70.171.85",
        "port": 46796,
        "username": "fttMws",
        "password": "ioGMdd",
        "protocol": "http",
    }
    url = format_proxy_url(proxy_data)
    assert url == "http://fttMws:ioGMdd@118.70.171.85:46796"


def test_proxy_url_formatter_without_auth() -> None:
    """Tests formatting proxy dictionary without credentials."""
    from src.infrastructure.tiktok.sammonny_adapter import format_proxy_url

    proxy_data = {
        "host": "192.168.1.100",
        "port": 8888,
        "username": None,
        "password": None,
        "protocol": "socks5",
    }
    url = format_proxy_url(proxy_data)
    # socks5h: hostnames are resolved by the proxy (socks5 resolved them locally: DNS leak).
    assert url == "socks5h://192.168.1.100:8888"


def test_default_session_factory_syncs_proxy(tmp_path: Any) -> None:
    """Tests that _default_session_factory fetches proxy from DB and syncs Preferences."""
    from src.infrastructure.tiktok.sammonny_adapter import _default_session_factory

    fake_profile = {
        "id": 25,
        "uuid": "fake-uuid-25",
        "proxy_id": 99,
        "cookies_browser": "sessionid=test_cookie; Domain=.tiktok.com",
    }
    fake_proxy = {
        "id": 99,
        "host": "10.0.0.1",
        "port": 3128,
        "username": "usr",
        "password": "pwd",
        "protocol": "http",
    }

    with patch("src.infrastructure.database.repositories.profile_repository.ProfileRepository.get_by_id", return_value=fake_profile), \
         patch("src.infrastructure.database.repositories.proxy_repository.ProxyRepository.get_by_id", return_value=fake_proxy), \
         patch("src.infrastructure.browser.orbita_launcher.OrbitaLauncher.sync_daemon_profile_proxy") as mock_sync, \
         patch("sammonny.engine.core.AntidetectEngine.session") as mock_engine_session:

        mock_raw_session = MagicMock()
        mock_raw_session.profile_id = "fake-uuid-25"
        mock_engine_session.return_value = mock_raw_session

        sess = _default_session_factory(25, db_path=tmp_path / "test.db")

        # Verify proxy was synced
        mock_sync.assert_called_once_with("fake-uuid-25", fake_proxy)

        # Verify session carries proxy_url and proxies dict
        assert hasattr(sess, "proxy_url")
        assert sess.proxy_url == "http://usr:pwd@10.0.0.1:3128"
        assert hasattr(sess, "proxies")
        assert sess.proxies == {
            "http": "http://usr:pwd@10.0.0.1:3128",
            "https": "http://usr:pwd@10.0.0.1:3128",
        }


def test_tos_upload_injects_proxies_into_requests_session() -> None:
    """Tests that execute_tos_upload uses proxy_url to configure requests.Session."""
    from sammonny.platforms.tiktok import TikTokPipeline

    pipe = TikTokPipeline(profile_id="test_prof")
    test_proxy = "http://user:pass@1.2.3.4:8080"

    with patch("requests.Session") as mock_sess_cls:
        mock_sess_instance = MagicMock()
        mock_sess_cls.return_value = mock_sess_instance

        # Call execute_tos_upload with proxy_url
        pipe.execute_tos_upload(
            upload_url="https://mock-upload.tiktokcdn.com/upload/v1/test",
            video_bytes=b"sample video bytes",
            proxy_url=test_proxy,
        )

        assert mock_sess_instance.proxies == {
            "http": test_proxy,
            "https": test_proxy,
        }


def test_find_file_input_in_flattened_nodes() -> None:
    """Tests helper locating input[type=file] across flattened CDP DOM nodes."""
    from sammonny.platforms.tiktok import TikTokHeadlessStudioUploader

    sample_flattened_nodes: list[dict[str, Any]] = [
        {"nodeId": 1, "nodeName": "HTML", "attributes": []},
        {"nodeId": 2, "nodeName": "BODY", "attributes": []},
        {"nodeId": 3, "nodeName": "IFRAME", "attributes": ["src", "https://tiktok.com/creator-center/upload"]},
        {"nodeId": 4, "nodeName": "DIV", "attributes": ["class", "dropzone"]},
        {"nodeId": 42, "nodeName": "INPUT", "attributes": ["type", "file", "accept", "video/*"]},
    ]

    target_id = TikTokHeadlessStudioUploader.extract_file_input_node_id(sample_flattened_nodes)
    assert target_id == 42


def test_find_file_input_returns_zero_when_absent() -> None:
    """Tests helper returns 0 when no file input node is present."""
    from sammonny.platforms.tiktok import TikTokHeadlessStudioUploader

    sample_flattened_nodes: list[dict[str, Any]] = [
        {"nodeId": 1, "nodeName": "HTML", "attributes": []},
        {"nodeId": 2, "nodeName": "DIV", "attributes": ["class", "container"]},
    ]

    target_id = TikTokHeadlessStudioUploader.extract_file_input_node_id(sample_flattened_nodes)
    assert target_id == 0


def test_captcha_detection_helper() -> None:
    """Tests detection of SecSDK captcha elements in DOM evaluate response."""
    from sammonny.platforms.tiktok import TikTokHeadlessStudioUploader

    mock_cdp = MagicMock()
    mock_cdp.evaluate.return_value = True

    uploader = TikTokHeadlessStudioUploader(MagicMock())
    assert uploader.check_captcha_present(mock_cdp) is True

    mock_cdp.evaluate.return_value = False
    assert uploader.check_captcha_present(mock_cdp) is False
