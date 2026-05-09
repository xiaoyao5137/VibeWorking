-- 020_add_detailed_content.sql
-- 为 bake_knowledge, bake_sops, bake_designs 添加 detailed_content 字段

-- 添加 detailed_content 到 bake_knowledge
ALTER TABLE bake_knowledge ADD COLUMN detailed_content TEXT;

-- 添加 detailed_content 到 bake_sops
ALTER TABLE bake_sops ADD COLUMN detailed_content TEXT;

-- 添加 detailed_content 到 designs
ALTER TABLE designs ADD COLUMN detailed_content TEXT;

-- 更新 FTS 触发器以包含 detailed_content

-- bake_knowledge FTS 触发器
DROP TRIGGER IF EXISTS bake_knowledge_fts_insert;
DROP TRIGGER IF EXISTS bake_knowledge_fts_update;

CREATE TRIGGER bake_knowledge_fts_insert AFTER INSERT ON bake_knowledge BEGIN
    INSERT INTO bake_knowledge_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

CREATE TRIGGER bake_knowledge_fts_update AFTER UPDATE ON bake_knowledge BEGIN
    DELETE FROM bake_knowledge_fts WHERE rowid = old.id;
    INSERT INTO bake_knowledge_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

-- bake_sops FTS 触发器
DROP TRIGGER IF EXISTS bake_sops_fts_insert;
DROP TRIGGER IF EXISTS bake_sops_fts_update;

CREATE TRIGGER bake_sops_fts_insert AFTER INSERT ON bake_sops BEGIN
    INSERT INTO bake_sops_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

CREATE TRIGGER bake_sops_fts_update AFTER UPDATE ON bake_sops BEGIN
    DELETE FROM bake_sops_fts WHERE rowid = old.id;
    INSERT INTO bake_sops_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

-- designs FTS 触发器
DROP TRIGGER IF EXISTS designs_fts_insert;
DROP TRIGGER IF EXISTS designs_fts_update;

CREATE TRIGGER designs_fts_insert AFTER INSERT ON designs BEGIN
    INSERT INTO designs_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

CREATE TRIGGER designs_fts_update AFTER UPDATE ON designs BEGIN
    DELETE FROM designs_fts WHERE rowid = old.id;
    INSERT INTO designs_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;
