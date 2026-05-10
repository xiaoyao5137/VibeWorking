-- 022_fix_bake_fts_delete_triggers.sql
-- FTS5 外部内容表不能用普通 DELETE 维护索引；需要写入 'delete' 指令行。

DROP TRIGGER IF EXISTS bake_knowledge_fts_insert;
DROP TRIGGER IF EXISTS bake_knowledge_fts_update;
DROP TRIGGER IF EXISTS bake_knowledge_fts_delete;

CREATE TRIGGER bake_knowledge_fts_insert AFTER INSERT ON bake_knowledge BEGIN
    INSERT INTO bake_knowledge_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

CREATE TRIGGER bake_knowledge_fts_update AFTER UPDATE ON bake_knowledge BEGIN
    INSERT INTO bake_knowledge_fts(bake_knowledge_fts, rowid, title, summary, content, entities)
    VALUES ('delete', old.id, old.title, old.summary, COALESCE(old.detailed_content, old.content, ''), old.entities);
    INSERT INTO bake_knowledge_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

CREATE TRIGGER bake_knowledge_fts_delete AFTER DELETE ON bake_knowledge BEGIN
    INSERT INTO bake_knowledge_fts(bake_knowledge_fts, rowid, title, summary, content, entities)
    VALUES ('delete', old.id, old.title, old.summary, COALESCE(old.detailed_content, old.content, ''), old.entities);
END;

DROP TRIGGER IF EXISTS bake_sops_fts_insert;
DROP TRIGGER IF EXISTS bake_sops_fts_update;
DROP TRIGGER IF EXISTS bake_sops_fts_delete;

CREATE TRIGGER bake_sops_fts_insert AFTER INSERT ON bake_sops BEGIN
    INSERT INTO bake_sops_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

CREATE TRIGGER bake_sops_fts_update AFTER UPDATE ON bake_sops BEGIN
    INSERT INTO bake_sops_fts(bake_sops_fts, rowid, title, summary, content, entities)
    VALUES ('delete', old.id, old.title, old.summary, COALESCE(old.detailed_content, old.content, ''), old.entities);
    INSERT INTO bake_sops_fts(rowid, title, summary, content, entities)
    VALUES (new.id, new.title, new.summary, COALESCE(new.detailed_content, new.content, ''), new.entities);
END;

CREATE TRIGGER bake_sops_fts_delete AFTER DELETE ON bake_sops BEGIN
    INSERT INTO bake_sops_fts(bake_sops_fts, rowid, title, summary, content, entities)
    VALUES ('delete', old.id, old.title, old.summary, COALESCE(old.detailed_content, old.content, ''), old.entities);
END;

DROP TRIGGER IF EXISTS bake_designs_fts_insert;
DROP TRIGGER IF EXISTS bake_designs_fts_update;
DROP TRIGGER IF EXISTS bake_designs_fts_delete;

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
