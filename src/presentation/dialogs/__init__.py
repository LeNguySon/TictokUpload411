"""
Presentation dialogs package exports.
"""

from src.presentation.dialogs.add_profile_dialog import AddProfileDialog
from src.presentation.dialogs.bulk_add_profile_dialog import BulkAddProfileDialog, parse_bulk_profile_line
from src.presentation.dialogs.project_dialog import ProjectManagerDialog
from src.presentation.dialogs.proxy_dialog import ProxyManagerDialog
from src.presentation.dialogs.trash_dialog import TrashDialog

__all__ = [
    "ProjectManagerDialog",
    "ProxyManagerDialog",
    "AddProfileDialog",
    "BulkAddProfileDialog",
    "TrashDialog",
    "parse_bulk_profile_line",
]
