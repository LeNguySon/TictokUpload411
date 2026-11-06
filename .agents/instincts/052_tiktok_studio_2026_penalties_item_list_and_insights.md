# 052 - TikTok Studio 2026 Telemetry: Modern Endpoints for Moderation, Items, and Monetization

## 1. Context & Motivation
Legacy endpoints (`/api/creator/item/list/`, `/api/creator/violation/list/`, `/api/creator/dashboard/overview/`) previously returned stale, inaccurate, or 404 responses for modern TikTok Studio accounts in 2026:
- Strikes were shown as 0/3 even when accounts suffered active Community Guidelines FYF removals.
- RPM was shown as inaccurate or missing because the Creator Rewards Program (CRP) status parsing did not handle status 2 (unmonetized/ineligible/pending).
- Video lists did not account for historical deleted/removed items vs public live items.

## 2. Authentic TikTok Studio 2026 Endpoint Mapping
Reverse-engineering TikTok Studio web bundles (`main.5cc4d756.js`, async chunk `5590.945fdef2.js`) uncovered the real production endpoints:

### A. Video & Item Management
- **Endpoint**: `POST https://www.tiktok.com/tiktok/creator/manage/item_list/v1/`
- **Payload**: `{"cursor": 0, "size": 50, "query": {}}`
- **Output**: Returns `item_list` array containing real video items, descriptions, creation timestamps, and metrics.

### B. Video Penalties & Community Guidelines (Originality / FYF Removal)
- **Endpoint**: `GET https://www.tiktok.com/mod/v1/getPenaltyDetails/?vid=<item_id>`
- **Output**: Returns `penalties` list (`penalty_id`, `reason_info_list`, `date`), and `appeal_status` (0 = `can_appeal`, 1 = `under_review`, 2 = `passed/none`).
- **Additional Transparency**: `GET https://www.tiktok.com/api/moderation/penalties/gettransparencypagecontent?entityId=<item_id>&enterFrom=`

### C. Channel Counter & Removed Videos Ratio
- **Endpoint**: `POST https://www.tiktok.com/tiktokstudio/api/web/counter/getHashCount`
- **Payload**: `{}`
- **Output**: `total_item_count` (all uploads in channel history) vs `item_count` (public active items). Delta represents deleted/removed videos.

### D. Traffic & Rewards Insights (RPM / VV History)
- **Endpoint**: `GET https://www.tiktok.com/tiktok/v1/analytics/insights/?type_requests=[{"insight_type":"INSIGHT_TYPE_ANALYTICS_OVERVIEW_REWARDS","data_date_range":"DATA_DATE_RANGE_7D"},{"insight_type":"INSIGHT_TYPE_ANALYTICS_OVERVIEW_VIEWS","data_date_range":"DATA_DATE_RANGE_7D"}]&time_offset=25200&is_dark_mode=false`
- **Monetization Handling**:
  - `analytics_overview_rewards.message.status == 2`: Creator is not actively monetized (pending, rejected, or un-enrolled). RPM must strictly evaluate to `0.00` and rewards to `0.00`.
  - `analytics_overview_views.list.value`: Sum of 7-day daily view values reflects real weekly video views (`views_month` / `total_views`).

## 3. Implementation Rules
1. Always route via `GoLoginTikTokClient` with assigned proxy or explicit `direct_connection=1`.
2. Parse cookies from DPAPI encrypted storage seamlessly.
3. Fall back gracefully to legacy endpoints if 2026 endpoints are throttled or unavailable.

