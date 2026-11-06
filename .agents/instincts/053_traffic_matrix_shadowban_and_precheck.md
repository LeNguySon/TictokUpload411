# 053 - Traffic Matrix, Shadowban Diagnostics, Optimal Posting Hours, and Pre-publish Content Check

## 1. Context & Motivation
Understanding channel health requires more than high-level follower or like counts. Creators need:
1. Proof of whether videos are being promoted to the For You feed or shadowbanned.
2. Accurate peak posting times based on when real followers/viewers are online.
3. Advance warning if video audio will be muted due to copyright before publishing.

## 2. Key Architecture & Endpoints

### A. Traffic Source Matrix & Shadowban Diagnostics
- **Endpoint**: `GET https://www.tiktok.com/tiktok/v1/analytics/insights/?type_requests=[{"insight_type":"INSIGHT_TYPE_ANALYTICS_OVERVIEW_TRAFFIC_SOURCE","data_date_range":"DATA_DATE_RANGE_7D"}]`
- **Metric Extraction**:
  - `For You`: If $\ge 70.0\%$, the account is in healthy organic distribution (`shadowban_status = 'safe'`).
  - If $< 20.0\%$, the account suffers algorithmic throttling or shadowban (`shadowban_status = 'shadowban'`).
  - `Search`, `Personal profile`, `Following`, `Sound` breakdown stored in `profiles.traffic_source_json`.

### B. Dynamic Optimal Posting Hour
- **Endpoint**: `INSIGHT_TYPE_ANALYTICS_VIEWER_ACTIVE_HOURS`
- **Output**: 24-hour array of online viewers.
- **Rule**: Calculate the hour index (0-23) with maximum viewer count. Store in `profiles.optimal_hour`.

### C. Audience Retention (New vs. Returning Viewers)
- **Endpoint**: `GET https://www.tiktok.com/aweme/v2/data/insight/?aid=1988&type_requests=[{"insigh_type":"new_viewer"},{"insigh_type":"returning_viewer"}]`
- **Calculation**: $\text{Retention Ratio} = \frac{\text{Returning Viewers}}{\text{Total Viewers}} \times 100\%$. Store in `profiles.retention_stats_json`.

### D. Pre-publish Content & Music Copyright Check
- **Endpoint**: `POST https://www.tiktok.com/tiktok/v1/creator/content/check/create`
- **Method**: `TikTokModerationService.precheck_video_content(profile_id, video_title)`
- **Safety**: Guarantees audio is clear and policy compliant before dispatching upload tasks.

## 3. UI Design Standards Enforcement
- In PyQt6 / QFluentWidgets, single `&` inside `QGroupBox` or `QLabel` is eaten by Qt as a keyboard mnemonic shortcut. Always use `&&` (e.g. `Ma Trận Nguồn View && Chẩn Đoán Phân Phối`).
- Never use raw Unicode emoji in UI chrome; adhere to `test_no_emoji_in_ui_chrome` and rely on Fluent Design card typography and colors.

