-- 015_split_knowledge_tables.sql
-- 将 knowledge_entries 拆分为 4 张表：
-- 1. episodic_memories - 情节记忆
-- 2. bake_articles - 提炼后的文章
-- 3. bake_knowledge - 提炼后的知识
-- 4. bake_sops - 提炼后的操作手册

-- 临时禁用外键约束以便迁移
PRAGMA foreign_keys = OFF;

-- 创建情节记忆表（保留原有字段）
CREATE TABLE episodic_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id INTEGER NOT NULL,
    summary TEXT NOT NULL,
    overview TEXT,
    details TEXT,
    entities TEXT,
    category TEXT,
    importance INTEGER DEFAULT 3,
    occurrence_count INTEGER DEFAULT 1,
    observed_at INTEGER,
    event_time_start INTEGER,
    event_time_end INTEGER,
    history_view INTEGER NOT NULL DEFAULT 0,
    content_origin TEXT,
    activity_type TEXT,
    is_self_generated INTEGER NOT NULL DEFAULT 0,
    evidence_strength TEXT,
    user_verified BOOLEAN DEFAULT 0,
    user_edited BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at_ms INTEGER,
    updated_at_ms INTEGER,
    capture_ids TEXT,
    start_time INTEGER,
    end_time INTEGER,
    duration_minutes INTEGER,
    frag_app_name TEXT,
    frag_win_title TEXT,
    FOREIGN KEY (capture_id) REFERENCES captures(id)
);

-- 创建 bake_articles 表
CREATE TABLE bake_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episodic_memory_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT,
    entities TEXT,
    importance INTEGER DEFAULT 3,
    user_verified BOOLEAN DEFAULT 0,
    user_edited BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at_ms INTEGER,
    updated_at_ms INTEGER,
    FOREIGN KEY (episodic_memory_id) REFERENCES episodic_memories(id) ON DELETE CASCADE
);

-- 创建 bake_knowledge 表
CREATE TABLE bake_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episodic_memory_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT,
    entities TEXT,
    importance INTEGER DEFAULT 3,
    user_verified BOOLEAN DEFAULT 0,
    user_edited BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at_ms INTEGER,
    updated_at_ms INTEGER,
    FOREIGN KEY (episodic_memory_id) REFERENCES episodic_memories(id) ON DELETE CASCADE
);

-- 创建 bake_sops 表
CREATE TABLE bake_sops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episodic_memory_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT,
    entities TEXT,
    importance INTEGER DEFAULT 3,
    user_verified BOOLEAN DEFAULT 0,
    user_edited BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at_ms INTEGER,
    updated_at_ms INTEGER,
    FOREIGN KEY (episodic_memory_id) REFERENCES episodic_memories(id) ON DELETE CASCADE
);

-- 迁移情节记忆数据（非 bake_* 类别）
INSERT INTO episodic_memories (
    id, capture_id, summary, overview, details, entities, category, importance,
    occurrence_count, observed_at, event_time_start, event_time_end,
    history_view, content_origin, activity_type, is_self_generated,
    evidence_strength, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms,
    capture_ids, start_time, end_time, duration_minutes, frag_app_name, frag_win_title
)
SELECT
    id, capture_id, summary, overview, details, entities, category, importance,
    occurrence_count, observed_at, event_time_start, event_time_end,
    history_view, content_origin, activity_type, is_self_generated,
    evidence_strength, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms,
    capture_ids, start_time, end_time, duration_minutes, frag_app_name, frag_win_title
FROM knowledge_entries
WHERE category NOT IN ('bake_article', 'bake_knowledge', 'bake_sop');

-- 迁移 bake_article 数据
INSERT INTO bake_articles (
    id, episodic_memory_id, title, summary, content, entities,
    importance, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms
)
SELECT
    id,
    COALESCE(json_extract(details, '$.source_knowledge_id'), capture_id) as episodic_memory_id,
    summary, overview, details, entities,
    importance, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms
FROM knowledge_entries
WHERE category = 'bake_article';

-- 迁移 bake_knowledge 数据
INSERT INTO bake_knowledge (
    id, episodic_memory_id, title, summary, content, entities,
    importance, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms
)
SELECT
    id,
    COALESCE(json_extract(details, '$.source_knowledge_id'), capture_id) as episodic_memory_id,
    summary, overview, details, entities,
    importance, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms
FROM knowledge_entries
WHERE category = 'bake_knowledge';

-- 迁移 bake_sop 数据
INSERT INTO bake_sops (
    id, episodic_memory_id, title, summary, content, entities,
    importance, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms
)
SELECT
    id,
    COALESCE(json_extract(details, '$.source_knowledge_id'), capture_id) as episodic_memory_id,
    summary, overview, details, entities,
    importance, user_verified, user_edited,
    created_at, updated_at, created_at_ms, updated_at_ms
FROM knowledge_entries
WHERE category = 'bake_sop';

-- 创建索引
CREATE INDEX idx_episodic_memories_capture_id ON episodic_memories(capture_id);
CREATE INDEX idx_episodic_memories_category ON episodic_memories(category);
CREATE INDEX idx_episodic_memories_importance ON episodic_memories(importance);
CREATE INDEX idx_episodic_memories_updated_at_ms ON episodic_memories(updated_at_ms);
CREATE INDEX idx_episodic_memories_is_self_generated ON episodic_memories(is_self_generated);

CREATE INDEX idx_bake_articles_episodic_memory_id ON bake_articles(episodic_memory_id);
CREATE INDEX idx_bake_articles_importance ON bake_articles(importance);
CREATE INDEX idx_bake_articles_updated_at_ms ON bake_articles(updated_at_ms);

CREATE INDEX idx_bake_knowledge_episodic_memory_id ON bake_knowledge(episodic_memory_id);
CREATE INDEX idx_bake_knowledge_importance ON bake_knowledge(importance);
CREATE INDEX idx_bake_knowledge_updated_at_ms ON bake_knowledge(updated_at_ms);

CREATE INDEX idx_bake_sops_episodic_memory_id ON bake_sops(episodic_memory_id);
CREATE INDEX idx_bake_sops_importance ON bake_sops(importance);
CREATE INDEX idx_bake_sops_updated_at_ms ON bake_sops(updated_at_ms);

-- 创建 FTS 表
CREATE VIRTUAL TABLE episodic_memories_fts USING fts5(
    summary, overview, details, entities,
    content=episodic_memories,
    content_rowid=id
);

CREATE VIRTUAL TABLE bake_articles_fts USING fts5(
    title, summary, content, entities,
    content=bake_articles,
    content_rowid=id
);

CREATE VIRTUAL TABLE bake_knowledge_fts USING fts5(
    title, summary, content, entities,
    content=bake_knowledge,
    content_rowid=id
);

CREATE VIRTUAL TABLE bake_sops_fts USING fts5(
    title, summary, content, entities,
    content=bake_sops,
    content_rowid=id
);

-- 填充 FTS 数据
INSERT INTO episodic_memories_fts(rowid, summary, overview, details, entities)
SELECT id, summary, overview, details, entities FROM episodic_memories;

INSERT INTO bake_articles_fts(rowid, title, summary, content, entities)
SELECT id, title, summary, content, entities FROM bake_articles;

INSERT INTO bake_knowledge_fts(rowid, title, summary, content, entities)
SELECT id, title, summary, content, entities FROM bake_knowledge;

INSERT INTO bake_sops_fts(rowid, title, summary, content, entities)
SELECT id, title, summary, content, entities FROM bake_sops;

-- 创建 FTS 触发器
CREATE TRIGGER episodic_memories_fts_insert AFTER INSERT ON episodic_memories BEGIN
    INSERT INTO episodic_memories_fts(rowid, summary, overview, details, entities)
    VALUES (new.id, new.summary, new.overview, new.details, new.entities);
END;

CREATE TRIGGER episodic_memories_fts_delete AFTER DELETE ON episodic_memories BEGIN
    DELETE FROM episodic_memories_fts WHERE rowid = old.id;
END;

CREATE TRIGGER episodic_memories_fts_update AFTER UPDATE ON episodic_memories BEGIN
    DELETE FROM episodic_memories_fts WHERE rowid = old.id;
    INSERT INTO episodic_memories_fts(rowid, summary, overview, details, entities)
    VALUES (new.id, new.summary, new.overview, new.details, new.entities);
END;

CREATE TRIGGER bake_articles_fts_insert AFTER INSERT ON bake_articles BEGIN
    INSERT INTO bake_articles_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, new.content, new.entities);
END;

CREATE TRIGGER bake_articles_fts_delete AFTER DELETE ON bake_articles BEGIN
    DELETE FROM bake_articles_fts WHERE rowid = old.id;
END;

CREATE TRIGGER bake_articles_fts_update AFTER UPDATE ON bake_articles BEGIN
    DELETE FROM bake_articles_fts WHERE rowid = old.id;
    INSERT INTO bake_articles_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, new.content, new.entities);
END;

CREATE TRIGGER bake_knowledge_fts_insert AFTER INSERT ON bake_knowledge BEGIN
    INSERT INTO bake_knowledge_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, new.content, new.entities);
END;

CREATE TRIGGER bake_knowledge_fts_delete AFTER DELETE ON bake_knowledge BEGIN
    DELETE FROM bake_knowledge_fts WHERE rowid = old.id;
END;

CREATE TRIGGER bake_knowledge_fts_update AFTER UPDATE ON bake_knowledge BEGIN
    DELETE FROM bake_knowledge_fts WHERE rowid = old.id;
    INSERT INTO bake_knowledge_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, new.content, new.entities);
END;

CREATE TRIGGER bake_sops_fts_insert AFTER INSERT ON bake_sops BEGIN
    INSERT INTO bake_sops_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, new.content, new.entities);
END;

CREATE TRIGGER bake_sops_fts_delete AFTER DELETE ON bake_sops BEGIN
    DELETE FROM bake_sops_fts WHERE rowid = old.id;
END;

CREATE TRIGGER bake_sops_fts_update AFTER UPDATE ON bake_sops BEGIN
    DELETE FROM bake_sops_fts WHERE rowid = old.id;
    INSERT INTO bake_sops_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, new.content, new.entities);
END;

-- 备份旧表（可选，用于回滚）
ALTER TABLE knowledge_entries RENAME TO knowledge_entries_backup;
ALTER TABLE knowledge_fts RENAME TO knowledge_fts_backup;

-- 重新启用外键约束
PRAGMA foreign_keys = ON;
