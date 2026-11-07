"""OrbitaLauncher.prepare_profile_environment wrote the same canvas/audio/WebGL/clientRects noises, media uid,
GPU, CPU/RAM and screen into EVERY profile's Preferences; it now writes the profile's own fingerprint."""

from __future__ import annotations

import json
from pathlib import Path

from src.domain.fingerprint.browser_fingerprint import generate_fingerprint, media_device_uid
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher


def _prefs(tmp_path: Path, profile: dict) -> dict:
    p_dir = tmp_path / profile["uuid"]
    OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe")).prepare_profile_environment(p_dir, profile)
    return json.loads((p_dir / "Default" / "Preferences").read_text(encoding="utf-8"))["gologin"]


def test_each_profile_gets_its_own_fingerprint_in_preferences(tmp_path: Path) -> None:
    a = _prefs(tmp_path, {"uuid": "uuid-pa", "name": "A"})
    b = _prefs(tmp_path, {"uuid": "uuid-pb", "name": "B"})
    fa = generate_fingerprint("uuid-pa")
    assert a["canvasNoise"] == fa["canvas_noise"]
    assert a["webglNoiseValue"] == fa["webgl_noise"]
    assert a["audioContext"]["noiseValue"] == fa["audio_noise"]
    assert a["webGl"]["renderer"] == fa["webgl"]["renderer"]
    assert a["hardwareConcurrency"] == fa["navigator"]["hardware_concurrency"]
    assert a["mediaDevices"]["uid"] == media_device_uid("uuid-pa")
    for key in ("canvasNoise", "webglNoiseValue", "getClientRectsNoice"):
        assert a[key] != b[key]
    assert a["mediaDevices"]["uid"] != b["mediaDevices"]["uid"]


def test_stored_fingerprint_wins_and_is_stable_across_launches(tmp_path: Path) -> None:
    fp = generate_fingerprint("stored-seed")
    profile = {"uuid": "uuid-pc", "name": "C", "fingerprint_json": json.dumps(fp)}
    first = _prefs(tmp_path, profile)
    second = _prefs(tmp_path, profile)
    assert first == second
    assert first["canvasNoise"] == fp["canvas_noise"] and first["userAgent"] == fp["navigator"]["user_agent"]


def test_no_shared_default_noise_constants_left() -> None:
    src = Path("src/infrastructure/browser/orbita_launcher.py").read_text(encoding="utf-8")
    for constant in ("91.240581", "5.793972911028913e-7", "2.14810925182", "e8046704b3cb45338099e2261bc1be67a1b2"):
        assert constant not in src
