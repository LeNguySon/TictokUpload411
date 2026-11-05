"""Admin (key issuer) GUI: signing keys, issuing keys for a machine code, ledger, backup/restore."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from src.infrastructure.licensing.verifier import decode_and_verify

MID = "ABCD-1234-EF56-7890"


@pytest.fixture
def admin(qtbot, tmp_path):
    from tools.license_issuer import issuer
    from tools.license_issuer.admin_gui import IssuerAdminWindow

    home = tmp_path / "issuer"
    kid, pub = issuer.keygen(home, kid="t1")
    trusted = {kid: pub}

    def make():
        win = IssuerAdminWindow(home=home, trusted=trusted)
        qtbot.addWidget(win)
        return win

    return make, home, trusted


def test_lists_signing_keys_and_marks_trusted(admin):
    make, _, trusted = admin
    win = make()
    assert win.cmb_kid.currentText().startswith("t1")
    assert win.txt_public_key.text() == trusted["t1"]
    assert win.lbl_trust.isHidden()  # key trusted by the app build: no warning


def test_issue_key_for_machine(admin):
    make, _, trusted = admin
    win = make()
    win.txt_sub.setText("Khách Admin")
    win.cmb_plan.setCurrentIndex(win.cmb_plan.findData("upload"))
    win.txt_mid.setText(MID.lower())  # lower-case pasted codes are accepted
    win.spin_days.setValue(90)
    win.txt_note.setText("đơn 42")
    win._on_issue()

    key = win.txt_output.toPlainText().strip()
    claims = decode_and_verify(key, trusted)
    assert claims.sub == "Khách Admin" and claims.plan.value == "upload" and claims.mid == MID
    assert claims.exp - claims.iat == 90 * 86400
    assert win.tbl_ledger.rowCount() == 1
    assert win.tbl_ledger.item(0, win.LEDGER_COLUMNS.index("sub")).text() == "Khách Admin"


def test_invalid_input_shows_error_and_issues_nothing(admin):
    make, home, _ = admin
    win = make()
    win.txt_sub.setText("X")
    win.txt_mid.setText("not-a-code")
    with patch("tools.license_issuer.admin_gui.InfoBar") as info:
        win._on_issue()
    info.error.assert_called_once()
    assert win.txt_output.toPlainText() == "" and not (home / "issued_licenses.csv").exists()


def test_untrusted_key_is_warned_and_blocks_issuing(admin, qtbot, tmp_path):
    from tools.license_issuer.admin_gui import IssuerAdminWindow

    _, home, _ = admin
    win = IssuerAdminWindow(home=home, trusted={})  # the app build does not trust t1
    qtbot.addWidget(win)
    assert not win.lbl_trust.isHidden() and not win.btn_issue.isEnabled()


def test_create_new_signing_key(admin):
    make, home, _ = admin
    win = make()
    with patch("tools.license_issuer.admin_gui.MessageBox"):
        win._on_keygen()
    assert win.cmb_kid.count() == 2
    assert (home / "signing_keys" / f"{win.current_kid()}.key").exists() and win.current_kid() != "t1"
    # The new key is not in the app build yet: labelled in the list, trusted one is not.
    assert "app chưa tin" in win.cmb_kid.currentText()
    assert win.cmb_kid.itemText(win.cmb_kid.findData("t1")) == "t1"


def test_create_new_signing_key_needs_confirmation(admin):
    make, home, _ = admin
    win = make()
    with patch("tools.license_issuer.admin_gui.MessageBox") as box:
        box.return_value.exec.return_value = False  # user clicks Hủy
        win._on_keygen()
    assert win.cmb_kid.count() == 1 and win.current_kid() == "t1"
    assert len(list((home / "signing_keys").glob("*.key"))) == 1


def test_untrusted_key_selected_on_start_falls_back_to_trusted(admin):
    from tools.license_issuer import issuer

    make, home, _ = admin
    issuer.keygen(home, kid="zz-untrusted")  # sorts after t1
    win = make()
    assert win.current_kid() == "t1" and win.btn_issue.isEnabled()


def test_backup_and_restore(admin, tmp_path):
    make, home, trusted = admin
    win = make()
    backup = tmp_path / "t1.pem"
    win._do_backup(backup, b"mat-khau-dai")
    assert b"ENCRYPTED" in backup.read_bytes()

    from tools.license_issuer.admin_gui import IssuerAdminWindow

    other = IssuerAdminWindow(home=tmp_path / "other", trusted=trusted)
    other._do_restore("t1", backup, b"mat-khau-dai")
    assert other.current_kid() == "t1"
