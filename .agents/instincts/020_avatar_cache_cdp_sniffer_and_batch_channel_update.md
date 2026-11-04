# Instinct 020 — Avatar Cache Subsystem, Live CDP Sniffer, and Batch Channel Update
## Learned from Gloglin2609 & SamMonny Antidetect SDK

### 1. Context & Motivation
1. **Avatar Rendering in Table**: Remote TikTok CDN URLs can expire or take 100-300ms to fetch, lagging table rendering and scrolling.
2. **Real-time API Sniffing**: While Orbita runs, the user or automation interacts with TikTok Web / Studio. We need to attach an event listener directly to the Playwright / CDP context to continuously harvest telemetry without polling.
3. **Batch Channel Setup**: Managing multiple accounts requires changing avatars, nicknames, and bio descriptions in bulk without repetitive manual input.

### 2. Core Technical Patterns Learned
1. **Avatar Caching Subsystem (`AvatarCacheService`)**:
   - Deterministic storage: `data/avatars/{profile_id}.jpg` (or `{storage_dir}/avatar.jpg`).
   - Downloads via `urllib` / `curl_cffi` using Chrome User-Agent on background worker threads.
   - Atomic file write: `.tmp` $\rightarrow$ `.jpg` to prevent partial corruption.
   - Updates `profiles.avatar_path` and `profiles.avatar_url`.
   - `CircularAvatarDelegate`: Draws antialiased smooth circular avatar (icon size 26px, radius 13px) with an in-memory pixmap cache for 60 FPS table performance.

2. **Live CDP Network Sniffer Attachment (`attach_playwright_sniffer`)**:
   - Binds `context_or_page.on("response", on_response)`.
   - URL filtering: `tiktok.com`, `byteoversea.com`, `ibytedtos.com`.
   - Route filtering: `/api/`, `/creator-center/api/`, `/passport/web/`, `/aweme/v1/`, etc.
   - Forwards HTTP 200 JSON payloads to `TikTokNetworkSniffer.process_api_response`.

3. **Spintax Engine & Batch Channel Update Dialog (`BatchChannelUpdateDialog`)**:
   - `spin_text`: Recursive resolution of nested Spintax `{Option 1|Option 2|{Sub A|Sub B}}`.
   - Fluent UI Dialog with independent toggles for Avatar, Nickname (`{index}` pattern), and Bio Spintax with a live preview button.
   - Dispatches `ChannelUpdateWorker` on `QThreadPool` for non-blocking execution.

### 3. Concurrency & UI Hygiene Invariants
- Scheduled timers (`self.scheduler_timer`) in `MainWindow` must be wrapped in `try...except` and stopped in `closeEvent` to prevent event-loop callback crashes against deleted temporary databases.
- `AppSignalBus` should be disconnected on window close and reset in `conftest.py` between test suites to eliminate cross-suite slot contamination.
