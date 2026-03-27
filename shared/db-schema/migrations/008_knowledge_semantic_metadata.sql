PRAGMA foreign_keys = ON;

ALTER TABLE vector_index ADD COLUMN observed_at INTEGER;
ALTER TABLE vector_index ADD COLUMN event_time_start INTEGER;
ALTER TABLE vector_index ADD COLUMN event_time_end INTEGER;
ALTER TABLE vector_index ADD COLUMN history_view INTEGER NOT NULL DEFAULT 0;
ALTER TABLE vector_index ADD COLUMN content_origin TEXT;
ALTER TABLE vector_index ADD COLUMN activity_type TEXT;
ALTER TABLE vector_index ADD COLUMN is_self_generated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE vector_index ADD COLUMN evidence_strength TEXT;

UPDATE vector_index
SET observed_at = COALESCE(observed_at, time, end_time, start_time),
    event_time_start = COALESCE(event_time_start, start_time),
    event_time_end = COALESCE(event_time_end, end_time),
    content_origin = COALESCE(content_origin, CASE WHEN source_type = 'knowledge' THEN 'live_interaction' ELSE NULL END),
    activity_type = COALESCE(activity_type, CASE
        WHEN category = '会议' THEN 'meeting'
        WHEN category = '代码' THEN 'coding'
        WHEN category = '文档' THEN 'reading'
        WHEN category = '聊天' THEN 'chat'
        ELSE 'other'
    END),
    evidence_strength = COALESCE(evidence_strength, CASE
        WHEN source_type = 'knowledge' THEN 'medium'
        ELSE NULL
    END);

CREATE INDEX IF NOT EXISTS idx_vector_index_observed_at ON vector_index(observed_at);
CREATE INDEX IF NOT EXISTS idx_vector_index_event_time ON vector_index(event_time_start, event_time_end);
CREATE INDEX IF NOT EXISTS idx_vector_index_activity_type ON vector_index(activity_type);
CREATE INDEX IF NOT EXISTS idx_vector_index_history_view ON vector_index(history_view);
CREATE INDEX IF NOT EXISTS idx_vector_index_self_generated ON vector_index(is_self_generated);

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES ('008_knowledge_semantic_metadata', CAST(strftime('%s', 'now') * 1000 AS INTEGER));
