"""
Reusable dialogs.

Measured on Windows: creating a NEW top-level window costs 45-110 ms of native work (a bare QDialog, whatever the
Qt platform options), so every dialog opened from scratch froze the GUI that long on top of its own setup.
Re-showing an existing hidden dialog takes ~0.2 ms. Dialogs that do not depend on the clicked row are therefore
created once (or pre-warmed while the app is idle) and re-shown; ``prepare_reopen(**kwargs)`` brings a reused
dialog up to date (reload data, clear secret inputs, reconnect signals) before it is shown again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from PyQt6 import sip
from PyQt6.QtWidgets import QDialog

logger = logging.getLogger(__name__)

D = TypeVar("D", bound=QDialog)


class DialogCache:
    def __init__(self) -> None:
        self._dialogs: dict[str, QDialog] = {}

    def _alive(self, key: str) -> QDialog | None:
        dlg = self._dialogs.get(key)
        if dlg is None or sip.isdeleted(dlg):
            self._dialogs.pop(key, None)
            return None
        return dlg

    def get(self, key: str, factory: Callable[[], D], **reopen_kwargs: Any) -> D:
        """The cached dialog for ``key`` brought up to date, or a new one built by ``factory``."""
        dlg = self._alive(key)
        if dlg is None:
            dlg = factory()
            self._dialogs[key] = dlg
            return dlg  # type: ignore[return-value]
        reopen = getattr(dlg, "prepare_reopen", None)
        if callable(reopen):
            reopen(**reopen_kwargs)
        return dlg  # type: ignore[return-value]

    def prewarm(self, key: str, factory: Callable[[], QDialog]) -> None:
        """Builds the dialog and its native window now (while idle), without showing it."""
        if self._alive(key) is not None:
            return
        try:
            dlg = factory()
            dlg.winId()  # creates the native window: the expensive part of a first show
            self._dialogs[key] = dlg
        except Exception as e:
            logger.debug("Dialog prewarm '%s' skipped: %s", key, e)

    def clear(self) -> None:
        for key in list(self._dialogs):
            dlg = self._alive(key)
            if dlg is not None:
                dlg.deleteLater()
        self._dialogs.clear()
