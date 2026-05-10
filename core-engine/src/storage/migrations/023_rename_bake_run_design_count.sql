-- 023_rename_bake_run_design_count.sql
-- 产品语言从 template 收敛到 design，运行统计列同步改名。
-- 用重建表代替 RENAME COLUMN，避免老 schema 里无效视图导致 SQLite 拒绝改列名。

PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS bake_runs_new;

CREATE TABLE bake_runs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_reason TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    completed_at INTEGER,
    processed_episode_count INTEGER NOT NULL DEFAULT 0,
    auto_created_count INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    discarded_count INTEGER NOT NULL DEFAULT 0,
    knowledge_created_count INTEGER NOT NULL DEFAULT 0,
    design_created_count INTEGER NOT NULL DEFAULT 0,
    sop_created_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    latency_ms INTEGER
);

INSERT INTO bake_runs_new (
    id, trigger_reason, status, started_at, completed_at,
    processed_episode_count, auto_created_count, candidate_count, discarded_count,
    knowledge_created_count, design_created_count, sop_created_count,
    error_message, latency_ms
)
SELECT
    id, trigger_reason, status, started_at, completed_at,
    processed_episode_count, auto_created_count, candidate_count, discarded_count,
    knowledge_created_count, template_created_count, sop_created_count,
    error_message, latency_ms
FROM bake_runs;

DROP TABLE bake_runs;
ALTER TABLE bake_runs_new RENAME TO bake_runs;

CREATE INDEX IF NOT EXISTS idx_bake_runs_started_at ON bake_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_bake_runs_status ON bake_runs(status);

PRAGMA foreign_keys = ON;
