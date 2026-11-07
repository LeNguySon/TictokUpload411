"""
Every profile needs its own browser fingerprint, fixed for its whole life. Measured on real data: 54/65 profiles
shared one user agent, webgl noise had a single value for all, and 7 of 16 profile folders carried the exact same
canvas/webgl/audio/GPU set (app defaults written by OrbitaLauncher.prepare_profile_environment).
"""

from __future__ import annotations

import json
import uuid

from src.domain.fingerprint import browser_fingerprint as bf

KEYS = ("canvas_noise", "audio_noise", "webgl_noise")


def test_same_seed_gives_the_same_fingerprint() -> None:
    seed = "1e555ac7-c8e5-45c2-9aef-55cbef78bf15"
    assert bf.generate_fingerprint(seed) == bf.generate_fingerprint(seed)


def test_fingerprints_are_unique_across_profiles() -> None:
    fps = [bf.generate_fingerprint(str(uuid.uuid4())) for _ in range(300)]
    noise_sets = {tuple(fp[k] for k in KEYS) for fp in fps}
    assert len(noise_sets) == 300
    assert len({bf.media_device_uid(str(i)) for i in range(300)}) == 300
    # realistic variety, not one hardware profile for everybody
    assert len({fp["webgl"]["renderer"] for fp in fps}) >= 6
    assert len({(fp["screen"]["width"], fp["screen"]["height"]) for fp in fps}) >= 4
    assert len({fp["navigator"]["hardware_concurrency"] for fp in fps}) >= 3


def test_fingerprint_is_coherent_windows_chrome() -> None:
    fp = bf.generate_fingerprint("seed-x", chrome_major=139)
    nav = fp["navigator"]
    assert nav["user_agent"] == (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
    assert nav["platform"] == "Win32" and fp["os"] == "win"
    assert nav["device_memory"] in (4, 8)  # navigator.deviceMemory is capped at 8
    vendor, renderer = fp["webgl"]["vendor"], fp["webgl"]["renderer"]
    brand = vendor.split("(")[1].rstrip(")")  # "Google Inc. (NVIDIA)" -> "NVIDIA"
    assert renderer.startswith(f"ANGLE ({brand},")


def test_profile_columns_store_the_whole_fingerprint() -> None:
    fp = bf.generate_fingerprint("seed-y")
    cols = bf.profile_columns(fp)
    assert json.loads(cols["fingerprint_json"]) == fp
    assert cols["user_agent"] == fp["navigator"]["user_agent"]
    assert cols["webgl_renderer"] == fp["webgl"]["renderer"]
    assert cols["canvas_noise"] == fp["canvas_noise"]
    assert cols["resolution"] == f"{fp['screen']['width']}x{fp['screen']['height']}"


def test_fingerprint_of_profile_prefers_stored_json_and_else_derives_from_uuid() -> None:
    stored = bf.generate_fingerprint("stored")
    assert bf.fingerprint_of({"uuid": "u1", "fingerprint_json": json.dumps(stored)}) == stored
    assert bf.fingerprint_of({"uuid": "u1"}) == bf.generate_fingerprint("u1")
    assert bf.fingerprint_of({"uuid": "u1", "fingerprint_json": "not json"}) == bf.generate_fingerprint("u1")


def test_gologin_preferences_come_from_the_profile_fingerprint() -> None:
    a = bf.gologin_preferences(bf.generate_fingerprint("a"), seed="a")
    b = bf.gologin_preferences(bf.generate_fingerprint("b"), seed="b")
    for key in ("canvasNoise", "webglNoiseValue", "userAgent"):
        assert key in a
    assert a["canvasNoise"] != b["canvasNoise"]
    assert a["audioContext"]["noiseValue"] != b["audioContext"]["noiseValue"]
    assert a["mediaDevices"]["uid"] != b["mediaDevices"]["uid"]
    assert a["getClientRectsNoice"] != b["getClientRectsNoice"]
