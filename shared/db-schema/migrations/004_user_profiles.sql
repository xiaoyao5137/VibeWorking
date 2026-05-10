-- 用户画像快照表
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_type TEXT NOT NULL CHECK(snapshot_type IN ('daily', 'weekly', 'monthly', 'yearly')),
    snapshot_date TEXT NOT NULL, -- ISO8601 date
    content TEXT NOT NULL, -- JSON: {roles, projects, responsibilities, work_style, creation_style}
    is_system_generated INTEGER NOT NULL DEFAULT 1, -- 0=用户编辑, 1=系统生成
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_profiles_type_date ON user_profiles(snapshot_type, snapshot_date DESC);
CREATE INDEX idx_profiles_created ON user_profiles(created_at DESC);
