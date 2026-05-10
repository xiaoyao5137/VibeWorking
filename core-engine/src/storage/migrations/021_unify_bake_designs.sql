-- 021_unify_bake_designs.sql
-- 清理历史过渡表：旧 designs 是写入黑洞，旧 bake_designs 是孤儿表。
-- 最终只保留由 bake_templates 重命名而来的 bake_designs。

PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS designs_fts_insert;
DROP TRIGGER IF EXISTS designs_fts_delete;
DROP TRIGGER IF EXISTS designs_fts_update;
DROP TABLE IF EXISTS designs_fts;
DROP TABLE IF EXISTS designs;

DROP TRIGGER IF EXISTS bake_designs_fts_insert;
DROP TRIGGER IF EXISTS bake_designs_fts_delete;
DROP TRIGGER IF EXISTS bake_designs_fts_update;
DROP TABLE IF EXISTS bake_designs_fts;
DROP TABLE IF EXISTS bake_designs;

DROP INDEX IF EXISTS idx_bake_templates_status;
DROP INDEX IF EXISTS idx_bake_templates_category;
DROP INDEX IF EXISTS idx_bake_templates_updated_at;
DROP INDEX IF EXISTS idx_bake_templates_review_status;
DROP INDEX IF EXISTS idx_bake_templates_creation_mode;

DROP TABLE IF EXISTS bake_templates;

CREATE TABLE bake_designs (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT    NOT NULL,
    category             TEXT    NOT NULL,
    status               TEXT    NOT NULL,
    tags                 TEXT    NOT NULL DEFAULT '[]',
    applicable_tasks     TEXT    NOT NULL DEFAULT '[]',
    source_memory_ids    TEXT    NOT NULL DEFAULT '[]',
    source_capture_ids   TEXT    NOT NULL DEFAULT '[]',
    source_episode_ids   TEXT    NOT NULL DEFAULT '[]',
    linked_knowledge_ids TEXT    NOT NULL DEFAULT '[]',
    structure_sections   TEXT    NOT NULL DEFAULT '[]',
    style_phrases        TEXT    NOT NULL DEFAULT '[]',
    replacement_rules    TEXT    NOT NULL DEFAULT '[]',
    prompt_hint          TEXT,
    detailed_content     TEXT,
    diagram_code         TEXT,
    image_assets         TEXT    NOT NULL DEFAULT '[]',
    usage_count          INTEGER NOT NULL DEFAULT 0,
    match_score          REAL,
    match_level          TEXT,
    creation_mode        TEXT    NOT NULL DEFAULT 'manual',
    review_status        TEXT    NOT NULL DEFAULT 'draft',
    evidence_summary     TEXT,
    generation_version   TEXT,
    deleted_at           INTEGER,
    created_at           INTEGER NOT NULL,
    updated_at           INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bake_designs_status ON bake_designs(status);
CREATE INDEX IF NOT EXISTS idx_bake_designs_category ON bake_designs(category);
CREATE INDEX IF NOT EXISTS idx_bake_designs_updated_at ON bake_designs(updated_at);
CREATE INDEX IF NOT EXISTS idx_bake_designs_review_status ON bake_designs(review_status);
CREATE INDEX IF NOT EXISTS idx_bake_designs_creation_mode ON bake_designs(creation_mode);

CREATE VIRTUAL TABLE IF NOT EXISTS bake_designs_fts USING fts5(
    name,
    category,
    structure_sections,
    style_phrases,
    replacement_rules,
    detailed_content,
    prompt_hint,
    content='bake_designs',
    content_rowid='id'
);

CREATE TRIGGER bake_designs_fts_insert AFTER INSERT ON bake_designs BEGIN
    INSERT INTO bake_designs_fts(
        rowid, name, category, structure_sections, style_phrases,
        replacement_rules, detailed_content, prompt_hint
    )
    VALUES (
        new.id, new.name, new.category, new.structure_sections, new.style_phrases,
        new.replacement_rules, new.detailed_content, new.prompt_hint
    );
END;

CREATE TRIGGER bake_designs_fts_delete AFTER DELETE ON bake_designs BEGIN
    INSERT INTO bake_designs_fts(
        bake_designs_fts, rowid, name, category, structure_sections, style_phrases,
        replacement_rules, detailed_content, prompt_hint
    )
    VALUES (
        'delete', old.id, old.name, old.category, old.structure_sections, old.style_phrases,
        old.replacement_rules, old.detailed_content, old.prompt_hint
    );
END;

CREATE TRIGGER bake_designs_fts_update AFTER UPDATE ON bake_designs BEGIN
    INSERT INTO bake_designs_fts(
        bake_designs_fts, rowid, name, category, structure_sections, style_phrases,
        replacement_rules, detailed_content, prompt_hint
    )
    VALUES (
        'delete', old.id, old.name, old.category, old.structure_sections, old.style_phrases,
        old.replacement_rules, old.detailed_content, old.prompt_hint
    );
    INSERT INTO bake_designs_fts(
        rowid, name, category, structure_sections, style_phrases,
        replacement_rules, detailed_content, prompt_hint
    )
    VALUES (
        new.id, new.name, new.category, new.structure_sections, new.style_phrases,
        new.replacement_rules, new.detailed_content, new.prompt_hint
    );
END;

PRAGMA foreign_keys = ON;
