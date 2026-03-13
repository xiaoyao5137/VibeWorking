-- =============================================================================
-- 迁移 004: 更新 FTS 索引以支持 overview 和 details 字段
-- 日期: 2026-03-09
-- 描述:
--   1. overview 和 details 字段已存在
--   2. 更新 FTS 索引以包含新字段
--   3. 重建触发器
-- =============================================================================

-- 1. 迁移现有数据：将 summary 复制到 overview（如果为空）
UPDATE knowledge_entries SET overview = summary WHERE overview IS NULL;

-- 2. 更新 FTS 索引以包含新字段
DROP TRIGGER IF EXISTS knowledge_ai;
DROP TRIGGER IF EXISTS knowledge_au;
DROP TRIGGER IF EXISTS knowledge_ad;
DROP TABLE IF EXISTS knowledge_fts;

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    overview,
    details,
    entities,
    content='knowledge_entries',
    content_rowid='id'
);

-- 3. 重建触发器
CREATE TRIGGER knowledge_ai AFTER INSERT ON knowledge_entries BEGIN
    INSERT INTO knowledge_fts(rowid, overview, details, entities)
    VALUES (new.id, new.overview, new.details, new.entities);
END;

CREATE TRIGGER knowledge_au AFTER UPDATE ON knowledge_entries BEGIN
    UPDATE knowledge_fts
    SET overview = new.overview,
        details = new.details,
        entities = new.entities
    WHERE rowid = new.id;
END;

CREATE TRIGGER knowledge_ad AFTER DELETE ON knowledge_entries BEGIN
    DELETE FROM knowledge_fts WHERE rowid = old.id;
END;

-- 4. 重新索引现有数据
INSERT INTO knowledge_fts(rowid, overview, details, entities)
SELECT id, overview, details, entities FROM knowledge_entries;
