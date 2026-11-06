"""
DDL Schemas for 24-table SQLite Database (Clean Architecture / Gloglin2609 Provenance).
"""

DDL_BASE_SCHEMAS = """
-- 1. Projects / Groups Table
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    color TEXT DEFAULT '#0078D4',
    video_folder TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Proxies Repository Table
CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT,
    password TEXT,
    protocol TEXT DEFAULT 'http' CHECK(protocol IN ('http', 'https', 'socks4', 'socks5')),
    proxy_type TEXT DEFAULT 'static' CHECK(proxy_type IN ('static', 'rotating')),
    status TEXT DEFAULT 'unchecked' CHECK(status IN ('alive', 'dead', 'unchecked', 'slow', 'leak_detected')),
    latency_ms INTEGER DEFAULT -1,
    public_ip TEXT,
    country_code TEXT,
    city TEXT,
    isp TEXT,
    timezone TEXT,
    latitude REAL,
    longitude REAL,
    change_ip_url TEXT,
    error_message TEXT,
    udp_supported INTEGER DEFAULT NULL,
    last_checked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(host, port, username)
);

CREATE INDEX IF NOT EXISTS idx_proxies_status ON proxies(status);
CREATE INDEX IF NOT EXISTS idx_proxies_country ON proxies(country_code);

-- 3. Profiles Core & Fingerprint Table
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    proxy_id INTEGER REFERENCES proxies(id) ON DELETE SET NULL,
    direct_connection INTEGER DEFAULT 0, -- 1 = user deliberately runs this profile from the host IP
    session_expires_at REAL, -- unix time the TikTok session cookie expires (NULL = unknown)
    cookies_synced_at TEXT, -- last time cookies_browser was read from the running browser
    storage_dir TEXT NOT NULL,
    status TEXT DEFAULT 'stopped' CHECK(status IN ('stopped', 'running', 'error', 'LIVE', 'DIE', 'CHECKPOINT')),

    -- Fingerprint Parameters
    user_agent TEXT NOT NULL,
    os_type TEXT DEFAULT 'win' CHECK(os_type IN ('win', 'mac', 'lin')),
    resolution TEXT DEFAULT '1920x1080',
    device_pixel_ratio REAL DEFAULT 1.0,
    cpu_cores INTEGER DEFAULT 8,
    memory_gb INTEGER DEFAULT 8,

    canvas_noise REAL DEFAULT 8.0,
    audio_noise REAL DEFAULT 0.0000009,
    client_rects_noise REAL DEFAULT 2.0,

    webgl_vendor TEXT,
    webgl_renderer TEXT,
    webgl_noise REAL DEFAULT 90.0,

    webrtc_mode TEXT DEFAULT 'noise' CHECK(webrtc_mode IN ('noise', 'disabled', 'real')),
    timezone_id TEXT DEFAULT 'UTC',
    color_scheme TEXT NOT NULL DEFAULT 'system' CHECK(color_scheme IN ('system', 'light', 'dark')),
    language_mode TEXT NOT NULL DEFAULT 'manual' CHECK(language_mode IN ('proxy', 'manual')),
    languages TEXT DEFAULT NULL,
    latitude REAL,
    longitude REAL,
    accuracy INTEGER DEFAULT 100,

    -- Session & Notes
    cookies_json TEXT,
    cookies_browser TEXT,
    notes TEXT,
    auth_2fa TEXT,
    is_trashed BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- TikTok MMO 28-Column Attributes
    username_on_tiktok TEXT,
    tiktok_user_id TEXT,
    nickname TEXT,
    avatar_url TEXT,
    avatar_path TEXT,
    total_followers INTEGER DEFAULT 0,
    total_following INTEGER DEFAULT 0,
    total_likes INTEGER DEFAULT 0,
    total_videos INTEGER DEFAULT 0,
    total_views INTEGER DEFAULT 0,
    views_month INTEGER DEFAULT 0,
    state_loggin_browser INTEGER DEFAULT 0,
    email TEXT,
    password TEXT,
    uore TEXT,
    reup_from TEXT,
    state_kyc TEXT DEFAULT 'No',
    money_earned REAL DEFAULT 0.0,
    rpm REAL DEFAULT 0.0,
    balance REAL DEFAULT 0.0,
    money_month REAL DEFAULT 0.0,
    date_reapply TEXT,
    appealViolateDate TEXT,
    ttl_violations TEXT,
    last_password TEXT,
    old_password TEXT,
    device_params TEXT,
    tags TEXT,
    totp_secret TEXT,
    tax_info TEXT,
    statistic_date_update TEXT,
    currency TEXT DEFAULT 'USD',
    country TEXT DEFAULT 'US',
    vat TEXT DEFAULT 'No',
    sec_uid TEXT,
    paypal_identity TEXT,
    minimum_pay REAL DEFAULT 0,
    folder_upload TEXT,
    music_bypass TEXT,
    email_backup TEXT,
    email_backup_password TEXT,
    account_standing TEXT DEFAULT 'Good',
    strike_count INTEGER DEFAULT 0,
    shadowban_status TEXT DEFAULT 'safe',
    shadowban_reasons TEXT,
    sdb TEXT DEFAULT '0',
    privacy INTEGER DEFAULT 1,
    total_penalty_points INTEGER DEFAULT 0,
    penalty_expire_date TEXT,
    account_appeal_status TEXT DEFAULT 'none',
    note_color TEXT DEFAULT '#FFFFFF',
    bio TEXT,
    user_rate INTEGER DEFAULT 0,
    commerce_user_level INTEGER DEFAULT 0,
    can_be_live_podcast INTEGER DEFAULT 0,
    bind_phone INTEGER DEFAULT 0,
    has_email INTEGER DEFAULT 0,
    channel_verdict TEXT DEFAULT 'unknown',
    vpn_config TEXT DEFAULT NULL,
    rx_bytes INTEGER DEFAULT 0,
    tx_bytes INTEGER DEFAULT 0,
    user_extensions TEXT DEFAULT NULL,
    refresh_token TEXT DEFAULT NULL,
    client_id TEXT DEFAULT NULL,
    cookie_email TEXT DEFAULT NULL,
    traffic_source_json TEXT DEFAULT NULL,
    optimal_hour INTEGER DEFAULT 12,
    retention_stats_json TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(name);
CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_trashed ON profiles(is_trashed);
CREATE INDEX IF NOT EXISTS idx_profiles_project ON profiles(project_id);
CREATE INDEX IF NOT EXISTS idx_profiles_page ON profiles(is_trashed, id DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_project_page ON profiles(is_trashed, project_id, id DESC);

-- 4. Profile Fonts Table
CREATE TABLE IF NOT EXISTS profile_fonts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    font_name TEXT NOT NULL,
    UNIQUE(profile_id, font_name)
);

-- 5. Activity Logs Table
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. TikTok Sessions Table
CREATE TABLE IF NOT EXISTS tiktok_sessions (
    profile_id INTEGER PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    cookies_json TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. TikTok Queue Table
CREATE TABLE IF NOT EXISTS tiktok_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    video_path TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','uploading','done','failed')),
    caption TEXT,
    schedule_time TEXT,
    privacy INTEGER DEFAULT 1,
    allow_comment INTEGER DEFAULT 1,
    allow_duet INTEGER DEFAULT 1,
    allow_stitch INTEGER DEFAULT 1,
    affiliate_product_id TEXT,
    error_reason TEXT,
    uploaded_on TEXT,
    video_id TEXT,
    screenshot_path TEXT,
    thumbnail_ratio REAL DEFAULT 0.25,
    allow_hd INTEGER DEFAULT 1,
    is_ai_generated INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Affiliate Products Table
CREATE TABLE IF NOT EXISTS affiliate_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL,
    title TEXT,
    commission REAL DEFAULT 0,
    price REAL DEFAULT 0,
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id, product_id)
);

-- 9. Statistic Table
CREATE TABLE IF NOT EXISTS statisticTable (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    id_video TEXT NOT NULL,
    title TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    whatsapp_shares INTEGER DEFAULT 0,
    engagement_rate REAL DEFAULT 0.0,
    traffic_flow TEXT,
    date_upload TEXT,
    red_line INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id, id_video)
);

-- 10. Phone Params Table
CREATE TABLE IF NOT EXISTS phoneParams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    device_id TEXT,
    iid TEXT,
    openudid TEXT,
    cdid TEXT,
    device_type TEXT,
    device_brand TEXT,
    model TEXT,
    os_version TEXT,
    resolution TEXT,
    dpi TEXT,
    mcc_mnc TEXT,
    user_agent TEXT,
    timezone_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id)
);

-- 11. Violate Videos Table
CREATE TABLE IF NOT EXISTS violateVideos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    video_id TEXT,
    title TEXT,
    violate_title TEXT,
    violate_description TEXT,
    video_posted_date TEXT,
    appeal_date TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id, video_id)
);

-- 12. Violate Profiles Table
CREATE TABLE IF NOT EXISTS violateProfiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    violate_title TEXT,
    violate_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id)
);

-- 13. Video Tables
CREATE TABLE IF NOT EXISTS videoTables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    title TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    whatsapp_shares INTEGER DEFAULT 0,
    engagement_rate REAL DEFAULT 0.0,
    traffic_flow TEXT,
    duration INTEGER DEFAULT 0,
    display INTEGER DEFAULT 1,
    schedule TEXT,
    upload_to TEXT,
    status TEXT DEFAULT 'active',
    thumbnail_url TEXT,
    allow_comment INTEGER DEFAULT 1,
    allow_duet INTEGER DEFAULT 1,
    allow_stitch INTEGER DEFAULT 1,
    is_pinned INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id, video_id)
);

-- 14. Account Appeals Table
CREATE TABLE IF NOT EXISTS accountAppeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    appeal_type TEXT DEFAULT 'account_ban',
    object_id TEXT,
    reason TEXT,
    contact_email TEXT,
    evidence_urls TEXT,
    status TEXT DEFAULT 'pending',
    notes TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. TikTok Report Observations Table
CREATE TABLE IF NOT EXISTS tiktok_report_observations (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    report_kind TEXT NOT NULL,
    observed_at TEXT,
    source TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'unverified',
    payload_json TEXT NOT NULL DEFAULT '{}',
    last_attempt_at TEXT NOT NULL,
    last_error TEXT,
    PRIMARY KEY(profile_id, report_kind)
);

-- 16. Video Registry (SHA256 Deduplication & Lock)
CREATE TABLE IF NOT EXISTS video_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_hash TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    status TEXT DEFAULT 'available' CHECK(status IN ('available', 'reserved', 'uploading', 'published', 'failed')),
    schedule_time TEXT DEFAULT NULL,
    assigned_profile_id INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
    published_profile_id INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
    tiktok_video_id TEXT,
    published_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_video_registry_hash ON video_registry(video_hash);
CREATE INDEX IF NOT EXISTS idx_video_registry_status ON video_registry(status);
CREATE INDEX IF NOT EXISTS idx_video_registry_assigned ON video_registry(assigned_profile_id);
CREATE INDEX IF NOT EXISTS idx_video_registry_schedule ON video_registry(status, schedule_time);
CREATE INDEX IF NOT EXISTS idx_report_observation_kind ON tiktok_report_observations(report_kind, status, observed_at);
CREATE INDEX IF NOT EXISTS idx_queue_ready ON tiktok_queue(status, schedule_time, profile_id);
CREATE INDEX IF NOT EXISTS idx_queue_profile ON tiktok_queue(profile_id, status);
CREATE INDEX IF NOT EXISTS idx_video_profile_status ON videoTables(profile_id, status);
CREATE INDEX IF NOT EXISTS idx_statistic_profile_date ON statisticTable(profile_id, date_upload);
CREATE INDEX IF NOT EXISTS idx_violation_profile_status ON violateVideos(profile_id, status, appeal_date);
CREATE INDEX IF NOT EXISTS idx_appeal_profile_status ON accountAppeals(profile_id, status);
"""
