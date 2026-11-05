"""Packaging: portable working dir for the exe, and the issuer tool never shipped in the customer app."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def test_frozen_exe_uses_its_own_folder_as_workdir(monkeypatch, tmp_path):
    import main

    exe_dir = tmp_path / "SonBetaPro"
    exe_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "SonBetaPro.exe"))
    cwd = os.getcwd()
    try:
        main.ensure_portable_workdir()
        assert Path(os.getcwd()).resolve() == exe_dir.resolve()
    finally:
        os.chdir(cwd)


def test_source_run_keeps_workdir(monkeypatch):
    import main

    monkeypatch.delattr(sys, "frozen", raising=False)
    cwd = os.getcwd()
    main.ensure_portable_workdir()
    assert os.getcwd() == cwd


def test_customer_app_spec_excludes_issuer_tool():
    spec = Path("packaging/tavm_app.spec").read_text(encoding="utf-8")
    assert '"tools"' in spec.split("excludes=")[1].split("]")[0]
    assert "license_issuer" not in spec


def test_build_outputs_are_git_ignored():
    ignored = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert "build/" in ignored and "dist/" in ignored
