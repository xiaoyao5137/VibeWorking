-- =============================================================================
-- 记忆面包 数据库查询工具视图
-- 迁移版本: 003_views
-- 描述: 创建常用的业务查询视图，供 Rust / Python 层直接使用
-- 依赖: 001_init.sql
-- =============================================================================

-- =============================================================================
-- 视图 1: v_recent_captures
-- 作用: 最近 24 小时内的非敏感采集记录（去除隐私内容）
-- 使用场景: UI 悬浮窗展示"今日工作轨迹"
-- =============================================================================
CREATE VIEW IF NOT EXISTS v_recent_captures AS
SELECT
    id,
    ts,
    datetime(ts / 1000, 'unixepoch', 'localtime') AS ts_local,
    app_name,
    win_title,
    COALESCE(ax_text, ocr_text) AS display_text,    -- 优先展示 ax_text
    event_type,
    screenshot_path
FROM captures
WHERE
    is_sensitive = 0
    AND ts >= (CAST(strftime('%s', 'now') AS INTEGER) - 86400) * 1000  -- 24小时内
ORDER BY ts DESC;


-- =============================================================================
-- 视图 2: v_app_activity_today
-- 作用: 今日各应用使用时长统计（按采集事件数量估算）
-- 使用场景: 设置页"今日活动"统计面板
-- =============================================================================
CREATE VIEW IF NOT EXISTS v_app_activity_today AS
SELECT
    app_name,
    COUNT(*)                        AS capture_count,
    MIN(ts)                         AS first_seen_ts,
    MAX(ts)                         AS last_seen_ts,
    (MAX(ts) - MIN(ts)) / 60000     AS active_minutes   -- 粗估活跃分钟数
FROM captures
WHERE
    is_sensitive = 0
    AND app_name IS NOT NULL
    AND ts >= (CAST(strftime('%s', 'now') AS INTEGER) - 86400) * 1000
GROUP BY app_name
ORDER BY capture_count DESC;


-- =============================================================================
-- 视图 3: v_action_stats
-- 作用: 自动化执行动作的成功率统计
-- 使用场景: 伴随式学习效果评估
-- =============================================================================
CREATE VIEW IF NOT EXISTS v_action_stats AS
SELECT
    app_name,
    action_type,
    COUNT(*)                                                AS total,
    SUM(CASE WHEN status = 'success'     THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN status = 'interrupted' THEN 1 ELSE 0 END) AS interrupted_count,
    SUM(CASE WHEN status = 'cancelled'   THEN 1 ELSE 0 END) AS cancelled_count,
    SUM(CASE WHEN user_correction IS NOT NULL THEN 1 ELSE 0 END) AS corrected_count,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS success_rate_pct
FROM action_logs
GROUP BY app_name, action_type
ORDER BY total DESC;


-- =============================================================================
-- 视图 4: v_style_sample_summary
-- 作用: 按场景汇总用户写作风格样本数量和平均质量
-- 使用场景: 个性化注入效果监控
-- =============================================================================
CREATE VIEW IF NOT EXISTS v_style_sample_summary AS
SELECT
    scene_type,
    COUNT(*)            AS sample_count,
    ROUND(AVG(quality), 2) AS avg_quality,
    SUM(word_count)     AS total_chars,
    MAX(ts)             AS latest_ts
FROM style_samples
GROUP BY scene_type
ORDER BY sample_count DESC;


-- =============================================================================
-- 视图 5: v_rag_session_summary
-- 作用: RAG 查询历史摘要
-- 使用场景: 历史查询回顾、Prompt 优化分析
-- =============================================================================
CREATE VIEW IF NOT EXISTS v_rag_session_summary AS
SELECT
    id,
    datetime(ts / 1000, 'unixepoch', 'localtime') AS ts_local,
    scene_type,
    SUBSTR(user_query, 1, 80)   AS query_preview,   -- 截取前80字符预览
    latency_ms,
    CASE WHEN user_feedback IS NULL THEN '满意' ELSE '已修改' END AS feedback_status
FROM rag_sessions
ORDER BY ts DESC;


-- =============================================================================
-- 记录本次迁移完成
-- =============================================================================
INSERT INTO schema_migrations (version, applied_at)
VALUES ('003_views', CAST(strftime('%s', 'now') * 1000 AS INTEGER));
