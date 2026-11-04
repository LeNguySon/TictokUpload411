"""
Unit tests for Assign Proxy feature and Context Menu (TSK: Assign Proxy & Crisp Icons).
Verifies:
1. ProfileRepository.bulk_assign_proxy assigns proxies atomically.
2. AssignProxyDialog populates proxies and updates database.
3. ProfileTableWidget emits update_proxy_requested signal.
"""

from pathlib import Path

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.dialogs.assign_proxy_dialog import AssignProxyDialog
from src.presentation.widgets.profile_table_widget import ProfileTableWidget


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Fixture providing initialized test database."""
    db_file = tmp_path / "test_assign_proxy.db"
    run_all_migrations(db_file)
    return db_file


def test_bulk_assign_proxy_repository(test_db_path: Path) -> None:
    """Verifies that bulk_assign_proxy updates proxy_id for multiple profiles."""
    profile_repo = ProfileRepository(test_db_path)
    proxy_repo = ProxyRepository(test_db_path)

    # 1. Create Proxy
    px_id = proxy_repo.create(host="103.1.2.3", port=8080, protocol="http")
    assert px_id > 0

    # 2. Create Profiles
    p1 = profile_repo.create({"name": "Profile 1"})
    p2 = profile_repo.create({"name": "Profile 2"})

    # 3. Bulk Assign
    updated_count = profile_repo.bulk_assign_proxy([p1, p2], px_id)
    assert updated_count == 2

    # 4. Verify in DB
    prof1 = profile_repo.get_by_id(p1)
    prof2 = profile_repo.get_by_id(p2)
    assert prof1 is not None and prof1["proxy_id"] == px_id
    assert prof2 is not None and prof2["proxy_id"] == px_id

    # 5. Unassign (None)
    profile_repo.bulk_assign_proxy([p1], None)
    prof1_unassigned = profile_repo.get_by_id(p1)
    assert prof1_unassigned is not None and prof1_unassigned["proxy_id"] is None


def test_assign_proxy_dialog_ui(qapp, test_db_path: Path) -> None:
    """Verifies AssignProxyDialog loads proxy items and applies selection."""
    profile_repo = ProfileRepository(test_db_path)
    proxy_repo = ProxyRepository(test_db_path)

    # Create proxies
    px_id = proxy_repo.create(
        host="192.168.1.50",
        port=9000,
        protocol="socks5",
        proxy_type="rotating",
    )
    p_id = profile_repo.create({"name": "Target Profile"})

    dialog = AssignProxyDialog(
        profile_ids=[p_id],
        profile_repo=profile_repo,
        proxy_repo=proxy_repo,
    )

    # Verify combo items (1 for None + 1 for created proxy = 2)
    assert dialog.combo_proxy.count() >= 2
    # Select the proxy
    dialog.combo_proxy.setCurrentIndex(1)
    assert dialog.combo_proxy.currentData() == px_id

    # Apply
    dialog._on_apply()

    # Verify profile was updated
    updated_profile = profile_repo.get_by_id(p_id)
    assert updated_profile is not None and updated_profile["proxy_id"] == px_id
    dialog.close()


def test_profile_table_widget_has_proxy_signal(qapp) -> None:
    """Verifies that ProfileTableWidget defines the update_proxy_requested signal."""
    table = ProfileTableWidget()
    assert hasattr(table, "update_proxy_requested")
