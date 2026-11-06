# 055 — Profile Storage Resolution & Chromium SQLite Cookie Auto-Login

## Context & Root Cause
In desktop antidetect browser architectures (Orbita / Chromium) managed alongside SamMonny GoLogin SDK:
1. Profiles created in local fallback or without daemon online were previously assigned relative virtual paths (`"profiles/{name}"`) without physically creating the underlying profile folder on disk (`mkdir(parents=True, exist_ok=True)`).
2. When launching the browser, `OrbitaLauncher` resolved relative paths against workspace `CWD` rather than the central daemon profile store (`daemon_profiles_dir()`), causing browser launches to spawn empty directories that lacked account history, fingerprint isolation, and cookies.
3. Pre-existing TikTok cookies (`cookies_json` / `cookie`) stored in the database were never injected upon launch, and existing `inject_to_chromium_sqlite` functions failed on fresh profiles because the `Default/Network/Cookies` SQLite file did not exist yet.
4. When users clicked "Mở thư mục hồ sơ" (Open profile folder), the UI hardcoded `~/.gologin/browser/`, yielding a "Thư Mục Không Tồn Tại" alert.

## Technical Resolution & Architecture
1. **Dynamic Chromium SQLite Cookie Initialization (`ensure_chromium_cookies_db`)**:
   - Location: `src/infrastructure/browser/cookie_injector.py`
   - Automatically initializes `Default/Network/Cookies` with:
     - `meta` table: `('version', '24')`, `('last_compatible_version', '24')`, `('mmap_status', '-1')`
     - `cookies` table: full 20-column schema matching Chromium 120-139 / Orbita engines.
   - Inserts cookies directly into SQLite with empty encrypted values (`encrypted_value = X''`) and plaintext `value` compatible with `--disable-encryption` and `--password-store=basic`.
   - Automatically unprotects Windows DPAPI envelopes (`gloglin:dpapi:v1:...`) before parsing and inserting.
2. **Authoritative Directory Resolution (`OrbitaLauncher.resolve_profile_dir`)**:
   - Location: `src/infrastructure/browser/orbita_launcher.py`
   - Evaluates:
     1. Absolute path check if existing.
     2. `daemon_profiles_dir() / uuid` if existing.
     3. `daemon_profiles_dir() / storage_dir.name` if existing.
     4. Workspace path if existing.
     5. If brand new, initializes `daemon_profiles_dir() / (uuid or name)` with `mkdir(parents=True, exist_ok=True)`.
3. **Pre-Launch Auto Cookie Injection**:
   - In `prepare_profile_environment`, extracts `cookies_json` / `cookie` / `cookies_browser` from `profile_data` and automatically invokes `BrowserCookieInjector.inject_to_chromium_sqlite(p_dir, cookie_raw)`.
4. **Explorer Open Folder Fix**:
   - In `MainWindow._on_open_profile_folder`, resolves target directory using `OrbitaLauncher.resolve_profile_dir(folder_or_name)`, ensuring 100% accurate Windows Explorer folder navigation.

