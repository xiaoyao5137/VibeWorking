-- 014_add_knowledge_timestamp_ms.sql
-- 为 knowledge_entries 添加毫秒级时间戳列，修复 bake pipeline 时间比较问题

-- 添加新列
ALTER TABLE knowledge_entries ADD COLUMN created_at_ms INTEGER;
ALTER TABLE knowledge_entries ADD COLUMN updated_at_ms INTEGER;

-- 迁移现有数据：将 TEXT 格式的时间戳转换为毫秒级 INTEGER
UPDATE knowledge_entries
SET created_at_ms = CAST((julianday(created_at) - 2440587.5) * 86400000 AS INTEGER)
WHERE created_at_ms IS NULL AND created_at IS NOT NULL;

UPDATE knowledge_entries
SET updated_at_ms = CAST((julianday(updated_at) - 2440587.5) * 86400000 AS INTEGER)
WHERE updated_at_ms IS NULL AND updated_at IS NOT NULL;

-- 为新列创建索引以优化 bake pipeline 查询
CREATE INDEX IF NOT EXISTS idx_knowledge_updated_at_ms ON knowledge_entries(updated_at_ms);
CREATE INDEX IF NOT EXISTS idx_knowledge_category_updated ON knowledge_entries(category, updated_at_ms);
