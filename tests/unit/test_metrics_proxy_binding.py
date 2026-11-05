"""
Unit Test Suite for Proxy Binding and IP Leak Prevention in TikTok Metrics Collection.
Strict TDD - Tier 4 Industrial Lifecycle.
Tests:
1. TikTokDirectPostClient query_creator_info accepts proxy_url and passes proxies dict.
2. SamMonnyTikTokAdapter resolves profile's proxy and injects formatted proxy_url.
3. SamMonnyTikTokAdapter rejects proxy marked as leak_detected with PermissionError.
4. PassiveTikTokSyncService guards against leak_detected proxies in DOM hydration.
5. MetricsSyncWorker handles deleted Qt signal bus safely without crashing.
"""

from unittest.mock import MagicMock, patch

import pytest
from sammonny.platforms.tiktok import TikTokDirectPostClient
from src.application.workers.metrics_sync_worker import MetricsSyncWorker
from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter


def test_direct_post_client_query_creator_info_passes_proxies():
    """Verifies that TikTokDirectPostClient passes the proxy dict to requests.Session."""
    client = TikTokDirectPostClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"error": {"code": "ok"}, "data": {"creator_username": "antigravity"}}

    with patch.object(client.session, "post", return_value=mock_resp) as mock_post:
        proxy_url = "http://user:pass@1.2.3.4:8080"
        result = client.query_creator_info(access_token="act_12345", proxy_url=proxy_url)

        assert result.get("creator_username") == "antigravity"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs.get("proxies") == {"http": proxy_url, "https": proxy_url}


def test_sammonny_adapter_fetch_creator_metrics_binds_profile_proxy():
    """Verifies that SamMonnyTikTokAdapter fetches the profile proxy and passes it to query_creator_info."""
    mock_prof_repo = MagicMock()
    mock_proxy_repo = MagicMock()
    mock_direct_client = MagicMock()

    mock_prof_repo.get_by_id.return_value = {"id": 25, "proxy_id": 10}
    mock_proxy_repo.get_by_id.return_value = {
        "id": 10,
        "host": "proxy.mmo.com",
        "port": 9000,
        "username": "u1",
        "password": "p1",
        "protocol": "http",
        "status": "active",
    }
    mock_direct_client.query_creator_info.return_value = {"creator_username": "david_mmo"}

    adapter = SamMonnyTikTokAdapter(
        profile_repo=mock_prof_repo,
        proxy_repo=mock_proxy_repo,
        direct_client=mock_direct_client,
    )

    with patch.object(adapter, "_sync_vault_token", return_value="vault_token_abc"):
        res = adapter.fetch_creator_metrics(profile_id=25)

        assert res.get("creator_username") == "david_mmo"
        mock_direct_client.query_creator_info.assert_called_once_with(
            "vault_token_abc",
            proxy_url="http://u1:p1@proxy.mmo.com:9000",
        )


def test_sammonny_adapter_rejects_leak_detected_proxy():
    """AgentShield Rule: Must reject any operation using a proxy flagged as leak_detected."""
    mock_prof_repo = MagicMock()
    mock_proxy_repo = MagicMock()
    mock_direct_client = MagicMock()

    mock_prof_repo.get_by_id.return_value = {"id": 25, "proxy_id": 10}
    mock_proxy_repo.get_by_id.return_value = {
        "id": 10,
        "host": "1.2.3.4",
        "port": 8080,
        "status": "leak_detected",
    }

    adapter = SamMonnyTikTokAdapter(
        profile_repo=mock_prof_repo,
        proxy_repo=mock_proxy_repo,
        direct_client=mock_direct_client,
    )

    with patch.object(adapter, "_sync_vault_token", return_value="vault_token_abc"):
        with pytest.raises(PermissionError) as exc_info:
            adapter.fetch_creator_metrics(profile_id=25)

        assert "LEAK DETECTED" in str(exc_info.value).upper()
        mock_direct_client.query_creator_info.assert_not_called()


def test_passive_sync_service_leak_guard():
    """Verifies that PassiveTikTokSyncService rejects tainted proxies during DOM extraction."""
    mock_prof_repo = MagicMock()
    mock_proxy_repo = MagicMock()

    mock_proxy_repo.get_by_id.return_value = {
        "id": 10,
        "host": "1.2.3.4",
        "port": 8080,
        "status": "leak_detected",
    }

    service = PassiveTikTokSyncService(
        profile_repo=mock_prof_repo,
        proxy_repo=mock_proxy_repo,
    )

    with patch("urllib.request.build_opener") as mock_opener:
        html = service._fetch_url_content("https://www.tiktok.com/@test", proxy_id=10)
        assert html == ""
        mock_opener.assert_not_called()


def test_metrics_sync_worker_safe_emit():
    """Verifies that MetricsSyncWorker does not crash if Qt signal bus is torn down."""
    mock_profile_service = MagicMock()
    mock_profile_service.sync_metrics_from_tiktok.return_value = {"status": "LIVE"}

    mock_signal_bus = MagicMock()
    mock_signal_bus.profile_updated.emit.side_effect = RuntimeError("C/C++ object deleted")

    worker = MetricsSyncWorker(
        profile_ids=[25],
        profile_service=mock_profile_service,
        signal_bus=mock_signal_bus,
    )

    # Calling execute must not crash despite RuntimeError from Qt signal bus
    worker.execute()
    mock_profile_service.sync_metrics_from_tiktok.assert_called_once_with(25)
