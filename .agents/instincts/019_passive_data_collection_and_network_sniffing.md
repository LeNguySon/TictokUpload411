# Instinct 019 — Passive Data Collection and Network Sniffing Upgrade
## Learned from Gloglin2609 & SamMonny Antidetect SDK

### 1. Context & Motivation
Directly issuing requests to TikTok endpoints from Python scripts or bots often triggers Captcha, rate-limits, or shadowbans. In contrast, passive telemetry snooping intercepts requests that the real antidetect browser (Orbita/GoLogin) already sends while navigating TikTok Studio and TikTok Web.

### 2. Core Technical Patterns Learned
1. **Offline Chromium SQLite Cookie Engine (SamMonny SDK Standard)**:
   - Expiration decoding uses Windows LDAP microsecond FileTime offset:
     $$\text{unix\_exp} = \frac{\text{expires\_utc} - 11644473600000000}{1\,000\,000.0}$$
   - Filter `.tiktok.com` domains in read-only SQLite URI mode (`?mode=ro`).
   - 9 Core Tokens monitored: `sessionid`, `sessionid_ss`, `sid_tt`, `sid_guard`, `uid_tt`, `tt_chain_token`, `passport_csrf_token`, `ttwid`, `store-idc`.
   - CSRF Equivalence: If `passport_csrf_token` is omitted but `tt_csrf_token` exists, map `passport_csrf_token = tt_csrf_token`.
   - State: `sessionid` or `sessionid_ss` present and non-expired $\rightarrow$ `state_loggin_browser = 1 (LIVE)`, else `0 (DIE)`.

2. **Item List Telemetry & 30-Day Rolling Window (`/api/creator/item/list`, `/api/post/item_list`)**:
   - Items payload contains embedded author information (`author` and `authorStats`). This allows updating channel username, follower count, total likes, and video count immediately without waiting for a `/api/user/detail/` call.
   - Dual-table persistence:
     - Aggregated statistics written to `statisticTable` (`profile_id, id_video, title, views, likes, comments, shares, engagement_rate`).
     - Rich metadata written to `videoTables` (`video_id, duration, display, thumbnail_url, allow_comment, allow_duet, allow_stitch, is_pinned, status`).
   - 30-day Rolling Views calculation:
     - For items with `create_time >= now - 30 * 86400`, sum `views` into `views_month` (Column 7 in Profile Table).

3. **Account Standing & Violations Snooping (`/api/creator/account/standing/`, `/api/creator/violation/`)**:
   - Extracts `standing_level` ("Good", "Warning", "Risk") and `active_strikes`.
   - Populates `violateVideos` table with `violate_title`, `violate_description`, `appeal_date`.
   - Updates `appealViolateDate` and `strike_count` in `profiles` table.

4. **Monetization & MMO Revenue Snooping (`/api/creator/dashboard/overview`, `/creator-center/api/creator/rewards`)**:
   - Parses `money_earned`, `rpm`, `balance`, `qualified_views`, `currency`, `date_reapply`, `state_kyc`.

### 3. Concurrency & UI Thread Invariant
Passive sniffing and SQLite parsing must never execute synchronously on the GUI Main Thread. It operates in `QThreadPool` via `MetricsSyncWorker` or CDP background interceptors, dispatching atomic updates through `AppSignalBus.profile_updated`.

