-- =============================================================================
-- WorkBuddy 数据库快速验证脚本
-- 使用方式: sqlite3 workbuddy.db < validate.sql
-- 描述: 验证表结构完整性、检查约束、输出基础统计
-- =============================================================================

-- 检查所有表是否存在（排除 sqlite 内部表和 FTS5 辅助表，保留 captures_fts 虚拟表本身）
SELECT
    CASE WHEN COUNT(*) = 10 THEN '✅ 所有表创建成功' ELSE '❌ 表数量异常: ' || COUNT(*) END AS check_tables
FROM sqlite_master
WHERE type IN ('table', 'shadow')
  AND name NOT LIKE 'sqlite_%'
  AND name NOT LIKE 'captures_fts_%';   -- 排除 FTS5 内部辅助表（_data/_idx/_config/_docsize）

-- 检查 FTS5 虚拟表
SELECT
    CASE WHEN COUNT(*) >= 1 THEN '✅ FTS5 全文索引存在' ELSE '❌ FTS5 索引缺失' END AS check_fts
FROM sqlite_master
WHERE type = 'table' AND name = 'captures_fts';

-- 检查所有触发器
SELECT
    CASE WHEN COUNT(*) = 3 THEN '✅ FTS5 触发器完整(3个)' ELSE '❌ 触发器数量异常: ' || COUNT(*) END AS check_triggers
FROM sqlite_master
WHERE type = 'trigger' AND name LIKE 'captures_fts_%';

-- 检查视图
SELECT
    CASE WHEN COUNT(*) = 5 THEN '✅ 视图创建完整(5个)' ELSE '❌ 视图数量异常: ' || COUNT(*) END AS check_views
FROM sqlite_master
WHERE type = 'view';

-- 检查默认偏好配置数量
SELECT
    CASE WHEN COUNT(*) >= 20 THEN '✅ 默认偏好配置完整 (' || COUNT(*) || '条)'
         ELSE '❌ 默认偏好配置不完整: ' || COUNT(*) || '条' END AS check_prefs
FROM user_preferences;

-- 检查默认应用黑名单
SELECT
    CASE WHEN COUNT(*) >= 5 THEN '✅ 默认应用黑名单完整 (' || COUNT(*) || '条)'
         ELSE '❌ 默认黑名单不完整: ' || COUNT(*) || '条' END AS check_filters
FROM app_filters WHERE filter_type = 'blacklist';

-- 检查 WAL 模式（journal_mode 是持久化设置，直接用 PRAGMA 查询）
SELECT
    CASE WHEN journal_mode = 'wal' THEN '✅ WAL 模式已开启' ELSE '❌ WAL 模式未开启: ' || journal_mode END AS check_wal
FROM pragma_journal_mode;

-- 外键约束是每次连接需显式开启的会话级设置，无法通过 validate.sql 直接验证
-- 由 Rust 应用层在初始化连接时执行：PRAGMA foreign_keys = ON;
SELECT '✅ 外键约束: 由应用层每次连接时开启（PRAGMA foreign_keys = ON）' AS check_fk;

-- 输出迁移记录
SELECT '--- 已执行的迁移 ---' AS info;
SELECT version, datetime(applied_at / 1000, 'unixepoch', 'localtime') AS applied_at_local
FROM schema_migrations
ORDER BY version;
