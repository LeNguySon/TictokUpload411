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


## item_list/v1: số liệu nằm ở cấp item, dạng chuỗi (kiểm chứng live @swall.pain, 2026-11-07)
- Mỗi item có `play_count`, `like_count`, `comment_count`, `share_count`, `favorite_count` là STRING ở cấp
  item (không có `stats{}`); `duration` tính bằng MILI-GIÂY; `create_time`/`post_time` là chuỗi epoch.
- Sniffer từng chỉ đọc `stats{}` / `views` ⇒ 50/50 video lưu 0 view ⇒ Radar engagement 0%, cảnh báo Flop giả.
  Nay `_first_count()` đọc cả hai nơi; duration ms ⇒ giây (`test_studio_item_list_stats.py`).

## Quét vi phạm, giờ đăng, avatar (kiểm chứng live @swall.pain, 2026-11-07)
- item_list/v1 có phân trang (`has_more`, `cursor`): kênh 79 video ⇒ 2 trang. Trước chỉ đọc trang đầu ⇒ 29 video
  không bao giờ được kiểm tra vi phạm. Nay `_list_all_items()` đọc hết (giới hạn ITEM_LIST_MAX_ITEMS).
- item_list KHÔNG có cờ nào cho biết video bị phạt (video bị gậy giống hệt video thường: status 102,
  visibility 1, permissions như nhau) ⇒ phải gọi getPenaltyDetails cho từng video; chạy song song
  PENALTY_LOOKUP_WORKERS=8 ⇒ 79 video ~36 s (trước 50 video tuần tự 85 s).
- `penalties[0].date` là epoch (chuỗi). Video đăng 01/09/2026, date = 08/09/2026, vẫn `can_appeal` ngày 07/11
  ⇒ khả năng đây là NGÀY BỊ PHẠT chứ không phải hạn kháng cáo (cột UI đang ghi "Hạn nộp đơn"). Hiển thị qua
  `format_appeal_deadline()` (dd/mm/YYYY).
- `optimal_hour` = giờ cao điểm người xem (insights VIEWER_ACTIVE_HOURS, 7 ngày, `time_offset=25200` ⇒ giờ VN).
  Kênh khán giả GB ⇒ cao điểm 01:00 VN (~19:00 UK); giá trị cũ 22 chỉ là dữ liệu cũ, không phải lỗi.
- Giờ đăng video: sniffer lưu `statisticTable.date_upload` (giờ máy, cùng múi với insights); Radar dùng
  `video_posted_hour()`; không có giờ ⇒ `fallback_best_hour=optimal_hour` thay vì 12 mặc định.
- Avatar đi qua `resolve_profile_egress` (quy tắc egress duy nhất): proxy, hoặc IP máy nếu `direct_connection=1`.
