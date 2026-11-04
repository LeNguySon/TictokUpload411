# Instinct 021: Profile Runtime Status Synchronization, "stop..." Elision Fix & Gloglin2609 Cookie E2E Integration

## 1. Context & Problem
- **Profile Column 12 Status Glitch**: Column "Tình trạng" kept displaying `stop...` even when browser windows were actively launched or closed by users.
- **Root Cause**:
  1. `OrbitaLauncher` had no session tracking for profiles launched through SamMonny GoLogin SDK (`gl.start()`), and relied on inspecting `.process.lock` via supervisor which is never written by the SamMonny daemon.
  2. `MainWindow.refresh_profiles()` immediately overwrote database `status="running"` back to `"stopped"` because `is_profile_running()` returned `False`.
  3. No background `QTimer` existed to monitor running processes when users closed browser windows via OS button 'X'.
  4. Column 12 text `"stopped"` was elided to `"stop..."` because column width was too narrow without explicit minimum width and tooltips.

## 2. Technical Solution
- **4-Layer Defense-in-Depth Process Detection**:
  1. *Subprocess Popen*: In-memory `proc.poll() is None`.
  2. *Socket Debugger Port Probe*: Sub-millisecond TCP check (`is_port_open(port)`) verifying remote debugging port `127.0.0.1:port` tracked in `_active_sdk_sessions`.
  3. *SamMonny Daemon API*: Querying `client.get_profile(uuid)` / `/api/v1/profiles` if daemon is running.
  4. *psutil Process Command-line Scan*: Inspecting running `chrome.exe` / `orbita.exe` for matching storage directory or UUID.
- **Real-Time Periodic Status Watcher**:
  - `MainWindow.profile_status_timer = QTimer(self)` (every 3000ms / 3s) scanning active profiles.
  - Granular row cell updates (`_update_profile_status_cell`) avoid full table redraws and GUI flickering.
  - Automatically dispatches `MetricsSyncWorker` upon detecting browser close to update `LIVE`/`DIE` account status.
- **Column 12 UI Formatting**:
  - Column width set to $\ge 115\text{px}$.
  - Full tooltips (`Trạng thái hoạt động: {status}`) and bold color styling (`running`: `#0078D4`, `stopped`: `#605E5C`, `LIVE`: `#107C41`, `DIE`: `#D83B01`, `CHECKPOINT`: `#CA5010`).

## 3. Gloglin2609 Real-World Cookie Extraction & E2E Validation
- **DPAPI Secret Protection**:
  - Gloglin2609 stores cookies with prefix `gloglin:dpapi:v1:`, protected by Windows DPAPI `CryptProtectData` with purpose `"database-secrets-v1"`.
  - Recovered using `core.secret_protection.unprotect_text`.
  - Extracted 51 authentic profiles with complete TikTok authentication sessions (`sessionid`, `sessionid_ss`, `sid_tt`, `ttwid`, `msToken`).
- **Proxy Audit**:
  - Tested `118.70.171.85:46796` and `118.70.171.101:50266`.
  - Both proxy endpoints are listening on HTTP protocol and returned `407 Proxy Authentication Required` (proxy server requires IP whitelist registration or credentials update on provider dashboard).
  - Saved credentials securely into `WindowsCredentialVault`.
