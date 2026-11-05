"""Contract checks between our code and the installed SamMonny SDK (1.8.1).

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
    adapter.publisher = MagicMock()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")

    with patch.object(MemoryManager, "trim_process_tree_memory") as trim:
        adapter.upload_video(profile_id=1, video_path=video, title="t")
    assert trim.call_count == 1
    assert inspect.signature(MemoryManager.trim_process_tree_memory).parameters.keys() == {"root_pid"}
