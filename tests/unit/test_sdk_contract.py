"""Contract checks between our code and the installed SamMonny SDK (1.8.5).

`sammonny.MemoryManager.trim_working_set()` does not exist in the SDK; the calls were swallowed by
try/except, so the documented post-task RAM trim never ran.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import sammonny
from sammonny.system.memory import MemoryManager


def test_no_code_calls_missing_memory_manager_api():
    offenders = [
        str(p)
        for p in Path("src").rglob("*.py")
        if "trim_working_set()" in p.read_text(encoding="utf-8") and "MemoryManager" in p.read_text(encoding="utf-8")
    ]
    assert not hasattr(sammonny.MemoryManager, "trim_working_set")
    assert offenders == [], f"MemoryManager.trim_working_set() does not exist in the SDK: {offenders}"


def test_base_worker_does_not_trim_after_every_task():
    """Workers run every few seconds (status sync); trimming the whole app each time pages the GUI out."""
    from src.application.workers.base_worker import BaseWorker

    class _W(BaseWorker):
        def execute(self) -> None:
            pass

    with patch.object(MemoryManager, "trim_process_tree_memory") as trim:
        _W().run()
    trim.assert_not_called()


def test_upload_trims_process_tree_once_with_real_sdk_api(tmp_path: Path):
    from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter

    vault = MagicMock()
    vault.get_oauth_tokens.return_value = None
    adapter = SamMonnyTikTokAdapter(vault=vault, db_path=tmp_path / "x.db", session_factory=MagicMock())
    adapter._profile_egress = lambda _pid: "http://proxy.test:8080"
    adapter.publisher = MagicMock()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")

    with patch.object(MemoryManager, "trim_process_tree_memory") as trim:
        adapter.upload_video(profile_id=1, video_path=video, title="t", privacy="PUBLIC_TO_EVERYONE")
    assert trim.call_count == 1
    assert inspect.signature(MemoryManager.trim_process_tree_memory).parameters.keys() == {"root_pid"}


def test_studio_post_click_can_use_random_in_sdk_tiktok_module():
    """Unreleased SDK main after 1.8.3 called random.uniform() in the Studio Post click without importing
    random: the NameError was swallowed and the post button never clicked (fixed in 1.8.4). The adapter keeps
    `random` bound whichever SDK build is installed."""
    import random

    import sammonny.platforms.tiktok as sdk_tiktok
    import src.infrastructure.tiktok.sammonny_adapter  # noqa: F401  (installs the compatibility shim)

    assert getattr(sdk_tiktok, "random", None) is random


def test_cookie_hybrid_stays_disabled_until_verified_live():
    """SDK 1.8.4 Hybrid no longer simulates: it needs a real VOD session and never falls back to the synthetic
    TOS session. Its VOD upload URL layout is still unverified against a live upload, so the app keeps Hybrid
    off. A build that again falls back to the synthetic session must never be enabled."""
    from sammonny.platforms.tiktok import TikTokHybridApiUploader
    from src.infrastructure.tiktok import sammonny_adapter

    hybrid_source = inspect.getsource(TikTokHybridApiUploader.upload_via_hybrid)
    assert "prepare_upload_session" not in hybrid_source, "SDK Hybrid falls back to the simulated TOS session again"
    assert sammonny_adapter.COOKIE_HYBRID_AVAILABLE is False


def test_daemon_client_can_update_fingerprints():
    """Right-click > Cập Nhật Vân Tay needs SamMonnyDaemonClient.update_fingerprint (SDK >= 1.8.5)."""
    from sammonny.core.client import SamMonnyDaemonClient

    params = inspect.signature(SamMonnyDaemonClient.update_fingerprint).parameters
    assert {"profile_id", "fingerprint", "regenerate", "os_name"} <= set(params)
