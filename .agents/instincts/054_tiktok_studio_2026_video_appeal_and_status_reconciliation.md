# 054 - TikTok Studio 2026 Video Appeal Workflow and Transparency Reconciliation

## 1. Context & Motivation
Legacy implementations of TikTok video strike appeals relied on deprecated URLs such as `/creator-center/api/violation/appeal` with basic `{item_id, appeal_reason}` payloads. In modern TikTok Studio (2026+), these routes fail or return 404/403. TikTok now enforces a strict multi-tier moderation penalty structure with dynamic transparency verification and unique `penaltyID` & `penaltySource` tracking.

## 2. Reverse-Engineered Architecture & Endpoints (TikTok Studio 2026)

### A. Pre-Appeal Transparency Check
- **Endpoint**: `GET https://www.tiktok.com/api/moderation/penalties/gettransparencypagecontent?entityId=<video_id>`
- **Response Fields**:
  - `showAppealBtn`: Boolean indicating if the video is currently appealable. If `False`, appeals must not be sent.
  - `appealDetails`: List of penalty items, e.g. `[{"penaltyID": "7682884793714252566", "penaltySource": 1}]`.
  - `transparencyModerationPageType`: Integer enum representing the moderation lifecycle stage:
    - `1`: `PenaltyDetailPage` (Penalty active; appeal button available)
    - `2`: `AppealRejectedPage` (Appeal was denied; strike stands)
    - `3`: `AppealReceivedPage` (Appeal received; currently under review)
    - `4`: `AppealExpiredPage` (Appeal deadline passed)
    - `5`: `AppealApprovedPage` (Appeal succeeded; strike removed!)
    - `6`: `AppealSubmittedPage` (Freshly submitted)

### B. Primary Submission Endpoint (SubmitAppealsV2)
- **Endpoint**: `POST https://www.tiktok.com/api/moderation/penalties/submitappeal`
- **Payload Schema**:
  ```json
  {
    "appealDetails": [{"penaltyID": "<penalty_id>", "penaltySource": 1}],
    "itemId": "<video_id>"
  }
  ```
- **Success Criteria**: `BaseResp.StatusCode == 0` or HTTP 200/201.

### C. Fallback Submission Endpoint (ModV1)
- **Endpoint**: `POST https://www.tiktok.com/mod/v1/submitAppeals`
- **Payload Schema**:
  ```json
  {
    "vid": "<video_id>",
    "appeal_details": "[{\"issuer\": \"TNS\", \"penalty_id\": \"<penalty_id>\"}]"
  }
  ```

### D. Automated Reconciliation
- `TikTokModerationService.check_appeal_status(profile_id)`:
  - Iterates through pending/appealed videos.
  - Calls `fetch_video_appeal_info(profile_id, video_id)`.
  - Reconciles database state:
    - `page_type == 5`: Sets `violateVideos.status = 'resolved'`, `accountAppeals.status = 'approved'`, refreshes standing.
    - `page_type == 2`: Sets `violateVideos.status = 'penalized'`, `accountAppeals.status = 'rejected'`.
    - `page_type in (3, 6)`: Sets `status = 'under_review'`.

