PRAGMA foreign_keys = ON;

ALTER TABLE system_metrics ADD COLUMN source TEXT;
ALTER TABLE system_metrics ADD COLUMN scope TEXT;
ALTER TABLE system_metrics ADD COLUMN target_name TEXT;
ALTER TABLE system_metrics ADD COLUMN target_pid INTEGER;
ALTER TABLE system_metrics ADD COLUMN target_pids_json TEXT;
ALTER TABLE system_metrics ADD COLUMN coverage_status TEXT;
ALTER TABLE system_metrics ADD COLUMN coverage_note TEXT;

CREATE INDEX IF NOT EXISTS idx_metrics_scope_ts ON system_metrics(scope, ts);
CREATE INDEX IF NOT EXISTS idx_metrics_source_ts ON system_metrics(source, ts);

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES ('006_monitor_metric_scopes', CAST(strftime('%s', 'now') * 1000 AS INTEGER));
