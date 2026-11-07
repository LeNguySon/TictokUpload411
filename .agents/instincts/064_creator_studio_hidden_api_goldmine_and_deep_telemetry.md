# Instinct 064: Creator Studio Hidden API Goldmine & Deep Telemetry Extraction

## 1. Bản Chất Kỹ Thuật (Root Phenomenon)
TikTok Creator Studio Web client sử dụng kiến trúc Webpack chia tách thành 100+ async chunks (`builder-runtime`, `main.js`, `8634.js`). Bên trong ẩn giấu các native endpoints không công khai cung cấp dữ liệu phân tích giá trị cao mà API chính thức (Official Open API) không cấp:
1. `/aweme/v2/data/insight/`:
   - Tham số truy vấn sử dụng typo nguyên bản của TikTok: `insigh_type` (không có chữ 't' ở cuối).
   - Truy vấn video: `[{"insigh_type": "item_search_terms", "aweme_id": "..."}, {"insigh_type": "video_traffic_source_percent_realtime", ...}, {"insigh_type": "video_retention_rate_realtime", ...}]`.
   - `item_search_terms`: Trả về top từ khóa tìm kiếm dẫn người xem vào video (SEO FYP).
   - `video_traffic_source_percent_realtime`: Phân bổ chính xác tỷ lệ For You, Search, Profile, Follow, Sound.
   - `video_retention_rate_realtime`: Trả về 122+ điểm giữ chân người xem từng giây (0s-122s) kèm tỷ lệ xem hết (`finish_rate`).
   - `follower_active_history_hours`: Ma trận 7 ngày x 24 giờ hoạt động của Followers, cho phép xác định đỉnh online (Peak Hour) và khung giờ vàng đăng video.
   - `viewer_also_watched_users` & `items`: Top 10 kênh và top video viral đối thủ mà khán giả đang theo dõi (kèm đường dẫn tải trực tiếp không watermark).
2. `/tiktok/v1/analytics/insights/`:
   - Dữ liệu nhân khẩu học (Demographics): Quốc gia, thành phố, độ tuổi, giới tính và tăng trưởng ròng theo từng ngày (`analytics_follower_net_followers`).
3. `/tiktok/v1/creator/ai_comment/analytics_overview`:
   - Phương thức: `POST` với payload `{"item_id": ..., "item_id_str": "..."}`.
   - Phân loại AI bình luận: Ý tưởng video tiếp theo (`Inspiration`), Lời khen (`Love`), Câu hỏi người xem (`Questions`).
4. `/tiktok/v1/creator/publish_setting/`:
   - `enable_auto_music_copyright_check`: Trạng thái quét bản quyền âm thanh.
   - `enable_auto_post_check`: Trạng thái quét tiêu chuẩn cộng đồng trước khi đăng.

## 2. Quy Tắc Triển Khai (Industrial Engineering Rules)
1. **Lưu trữ CSDL an toàn**:
   - `profiles`: Thêm `audience_demographics_json`, `optimal_posting_hours_json`, `competitor_intelligence_json`, `publish_settings_json`.
   - `videoTables`: Thêm `search_terms_json`, `traffic_sources_json`, `retention_points_json`, `finish_rate`, `viewer_locations_json`, `ai_comments_json`.
   - Bảng chuyên dụng: `video_deep_analytics` với khóa chính `aweme_id`.
2. **Smart Scheduling**:
   - Trong `ScheduleVideoDialog`: Luôn tự động đọc `optimal_posting_hours_json` hoặc `optimal_hour` của profile đang chọn để hiển thị huy hiệu giờ vàng và nút 1-click đặt lịch vào đỉnh hoạt động tiếp theo.
3. **Chống sập giao diện (ScrollArea & Non-blocking)**:
   - Các dialog chứa nhiều metadata như `ChannelRadarDialog` bắt buộc phải bọc nội dung trong `QScrollArea(setWidgetResizable=True)` để không tràn màn hình trên độ phân giải nhỏ.
