"""
Central Typed PyQt6 Signal Bus for cross-thread event dispatching.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class AppSignalBus(QObject):
    """
    Application-wide singleton event bus carrying typed signals between
    background QRunnable workers and the PyQt6 main GUI thread.
    """

    _instance: "AppSignalBus | None" = None

    # Upload pipeline signals
    upload_started = pyqtSignal(int, int)  # video_id, profile_id
    upload_progress = pyqtSignal(int, int, int, float)  # video_id, bytes_uploaded, total_bytes, percentage
    upload_completed = pyqtSignal(int, str)  # video_id, publish_id
    upload_failed = pyqtSignal(int, str)  # video_id, error_message

    # Proxy signals
    proxy_checked = pyqtSignal(int, bool, float, str)  # proxy_id, is_alive, latency_ms, status_or_error
    proxy_leak_detected = pyqtSignal(int, str)  # proxy_id, reason

    # Profile & MMO signals
    profile_updated = pyqtSignal(int, dict)  # profile_id, updated_fields
    profile_trashed = pyqtSignal(int)  # profile_id
    profile_restored = pyqtSignal(int)  # profile_id

    # System UI notifications
    system_toast = pyqtSignal(str, str, str)  # title, content, type ("info", "success", "warning", "error")
    stats_aggregated = pyqtSignal(dict)  # aggregated summary dict

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def instance(cls) -> "AppSignalBus":
        if cls._instance is not None:
            try:
                import shiboken6

                if not shiboken6.isValid(cls._instance):
                    cls._instance = None
            except Exception:
                pass

        if cls._instance is not None:
            try:
                _ = cls._instance.signalsBlocked()
            except (RuntimeError, Exception):
                cls._instance = None

        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
