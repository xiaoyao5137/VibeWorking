use rusqlite::{params, Connection};

use crate::storage::{
    db::current_ts_ms,
    error::StorageError,
    models_bake::{BakeDesignRecord, NewBakeDesign},
    StorageManager,
};

impl StorageManager {
    pub fn insert_bake_design(&self, design: &NewBakeDesign) -> Result<i64, StorageError> {
        self.with_conn(|conn| insert_bake_design_inner(conn, design))
    }

    pub fn get_bake_design(&self, id: i64) -> Result<Option<BakeDesignRecord>, StorageError> {
        self.with_conn(|conn| {
            let mut stmt = conn.prepare(
                "SELECT id, name, category, status, tags, applicable_tasks, source_memory_ids,
                        source_capture_ids, source_episode_ids, linked_knowledge_ids,
                        structure_sections, style_phrases, replacement_rules,
                        prompt_hint, detailed_content, diagram_code, image_assets, usage_count,
                        match_score, match_level, creation_mode, review_status,
                        evidence_summary, generation_version, deleted_at,
                        created_at, updated_at
                 FROM bake_designs WHERE id = ?1",
            )?;
            let mut rows = stmt.query(params![id])?;
            if let Some(row) = rows.next()? {
                Ok(Some(row_to_bake_design(row)?))
            } else {
                Ok(None)
            }
        })
    }

    pub fn list_bake_designs_paginated(
        &self,
        query: Option<&str>,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<BakeDesignRecord>, StorageError> {
        self.with_conn(|conn| {
            let mut sql = String::from(
                "SELECT id, name, category, status, tags, applicable_tasks, source_memory_ids,
                        source_capture_ids, source_episode_ids, linked_knowledge_ids,
                        structure_sections, style_phrases, replacement_rules,
                        prompt_hint, detailed_content, diagram_code, image_assets, usage_count,
                        match_score, match_level, creation_mode, review_status,
                        evidence_summary, generation_version, deleted_at,
                        created_at, updated_at
                 FROM bake_designs WHERE deleted_at IS NULL",
            );
            let mut bind_values: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
            if let Some(q) = query {
                sql.push_str(
                    " AND (name LIKE ? OR category LIKE ? OR COALESCE(prompt_hint, '') LIKE ?)",
                );
                let pattern = format!("%{}%", q);
                bind_values.push(Box::new(pattern.clone()));
                bind_values.push(Box::new(pattern.clone()));
                bind_values.push(Box::new(pattern));
            }
            sql.push_str(" ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?");
            bind_values.push(Box::new(limit as i64));
            bind_values.push(Box::new(offset as i64));

            let mut stmt = conn.prepare(&sql)?;
            let params: Vec<&dyn rusqlite::ToSql> =
                bind_values.iter().map(|b| b.as_ref()).collect();
            let rows = stmt.query_map(params.as_slice(), |row| {
                Ok(row_to_bake_design(row).map_err(|_| rusqlite::Error::InvalidQuery)?)
            })?;
            rows.collect::<Result<Vec<_>, _>>()
                .map_err(StorageError::Sqlite)
        })
    }

    pub fn count_bake_designs_filtered(&self, query: Option<&str>) -> Result<i64, StorageError> {
        self.with_conn(|conn| {
            let mut sql =
                String::from("SELECT COUNT(*) FROM bake_designs WHERE deleted_at IS NULL");
            let mut bind_values: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
            if let Some(q) = query {
                sql.push_str(
                    " AND (name LIKE ? OR category LIKE ? OR COALESCE(prompt_hint, '') LIKE ?)",
                );
                let pattern = format!("%{}%", q);
                bind_values.push(Box::new(pattern.clone()));
                bind_values.push(Box::new(pattern.clone()));
                bind_values.push(Box::new(pattern));
            }

            let mut stmt = conn.prepare(&sql)?;
            let params: Vec<&dyn rusqlite::ToSql> =
                bind_values.iter().map(|b| b.as_ref()).collect();
            stmt.query_row(params.as_slice(), |row| row.get(0))
                .map_err(StorageError::Sqlite)
        })
    }

    pub fn list_bake_designs(&self) -> Result<Vec<BakeDesignRecord>, StorageError> {
        self.with_conn(|conn| {
            let mut stmt = conn.prepare(
                "SELECT id, name, category, status, tags, applicable_tasks, source_memory_ids,
                        source_capture_ids, source_episode_ids, linked_knowledge_ids,
                        structure_sections, style_phrases, replacement_rules,
                        prompt_hint, detailed_content, diagram_code, image_assets, usage_count,
                        match_score, match_level, creation_mode, review_status,
                        evidence_summary, generation_version, deleted_at,
                        created_at, updated_at
                 FROM bake_designs
                 WHERE deleted_at IS NULL
                 ORDER BY updated_at DESC, id DESC",
            )?;
            let rows = stmt.query_map([], |row| {
                Ok(row_to_bake_design(row).map_err(|_| rusqlite::Error::InvalidQuery)?)
            })?;
            rows.collect::<Result<Vec<_>, _>>()
                .map_err(StorageError::Sqlite)
        })
    }

    pub fn update_bake_design(
        &self,
        id: i64,
        design: &NewBakeDesign,
    ) -> Result<bool, StorageError> {
        let updated_at = current_ts_ms();
        self.with_conn(|conn| {
            let affected = conn.execute(
                "UPDATE bake_designs
                 SET name = ?1, category = ?2, status = ?3, tags = ?4, applicable_tasks = ?5,
                     source_memory_ids = ?6, source_capture_ids = ?7, source_episode_ids = ?8,
                     linked_knowledge_ids = ?9, structure_sections = ?10,
                     style_phrases = ?11, replacement_rules = ?12, prompt_hint = ?13,
                     detailed_content = ?14, diagram_code = ?15, image_assets = ?16,
                     usage_count = ?17, match_score = ?18, match_level = ?19,
                     creation_mode = ?20, review_status = ?21, evidence_summary = ?22,
                     generation_version = ?23, deleted_at = ?24, updated_at = ?25
                 WHERE id = ?26",
                params![
                    design.name,
                    design.category,
                    design.status,
                    design.tags,
                    design.applicable_tasks,
                    design.source_memory_ids,
                    design.source_capture_ids,
                    design.source_episode_ids,
                    design.linked_knowledge_ids,
                    design.structure_sections,
                    design.style_phrases,
                    design.replacement_rules,
                    design.prompt_hint,
                    design.detailed_content,
                    design.diagram_code,
                    design.image_assets,
                    design.usage_count,
                    design.match_score,
                    design.match_level,
                    design.creation_mode,
                    design.review_status,
                    design.evidence_summary,
                    design.generation_version,
                    design.deleted_at,
                    updated_at,
                    id,
                ],
            )?;
            Ok(affected > 0)
        })
    }

    pub fn toggle_bake_design_status(
        &self,
        id: i64,
    ) -> Result<Option<BakeDesignRecord>, StorageError> {
        let maybe_design = self.get_bake_design(id)?;
        let Some(design) = maybe_design else {
            return Ok(None);
        };

        let next_status = if design.status == "enabled" {
            "disabled"
        } else {
            "enabled"
        };
        let updated_at = current_ts_ms();
        self.with_conn(|conn| {
            conn.execute(
                "UPDATE bake_designs SET status = ?1, updated_at = ?2 WHERE id = ?3",
                params![next_status, updated_at, id],
            )?;
            Ok(())
        })?;

        self.get_bake_design(id)
    }

    pub fn soft_delete_bake_design(&self, id: i64) -> Result<bool, StorageError> {
        let deleted_at = current_ts_ms();
        self.with_conn(|conn| {
            let affected = conn.execute(
                "UPDATE bake_designs SET deleted_at = ?1, updated_at = ?1 WHERE id = ?2 AND deleted_at IS NULL",
                params![deleted_at, id],
            )?;
            Ok(affected > 0)
        })
    }
}

fn insert_bake_design_inner(
    conn: &Connection,
    design: &NewBakeDesign,
) -> Result<i64, StorageError> {
    let now = current_ts_ms();
    conn.execute(
        "INSERT INTO bake_designs (
            name, category, status, tags, applicable_tasks, source_memory_ids,
            source_capture_ids, source_episode_ids, linked_knowledge_ids,
            structure_sections, style_phrases, replacement_rules, prompt_hint, detailed_content, diagram_code,
            image_assets, usage_count, match_score, match_level, creation_mode, review_status,
            evidence_summary, generation_version, deleted_at, created_at, updated_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19, ?20, ?21, ?22, ?23, ?24, ?25, ?26)",
        params![
            design.name,
            design.category,
            design.status,
            design.tags,
            design.applicable_tasks,
            design.source_memory_ids,
            design.source_capture_ids,
            design.source_episode_ids,
            design.linked_knowledge_ids,
            design.structure_sections,
            design.style_phrases,
            design.replacement_rules,
            design.prompt_hint,
            design.detailed_content,
            design.diagram_code,
            design.image_assets,
            design.usage_count,
            design.match_score,
            design.match_level,
            design.creation_mode,
            design.review_status,
            design.evidence_summary,
            design.generation_version,
            design.deleted_at,
            now,
            now,
        ],
    )?;
    Ok(conn.last_insert_rowid())
}

fn row_to_bake_design(row: &rusqlite::Row<'_>) -> Result<BakeDesignRecord, StorageError> {
    Ok(BakeDesignRecord {
        id: row.get(0)?,
        name: row.get(1)?,
        category: row.get(2)?,
        status: row.get(3)?,
        tags: row.get(4)?,
        applicable_tasks: row.get(5)?,
        source_memory_ids: row.get(6)?,
        source_capture_ids: row.get(7)?,
        source_episode_ids: row.get(8)?,
        linked_knowledge_ids: row.get(9)?,
        structure_sections: row.get(10)?,
        style_phrases: row.get(11)?,
        replacement_rules: row.get(12)?,
        prompt_hint: row.get(13)?,
        detailed_content: row.get(14)?,
        diagram_code: row.get(15)?,
        image_assets: row.get(16)?,
        usage_count: row.get(17)?,
        match_score: row.get(18)?,
        match_level: row.get(19)?,
        creation_mode: row.get(20)?,
        review_status: row.get(21)?,
        evidence_summary: row.get(22)?,
        generation_version: row.get(23)?,
        deleted_at: row.get(24)?,
        created_at: row.get(25)?,
        updated_at: row.get(26)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_mgr() -> StorageManager {
        StorageManager::open_in_memory().expect("内存数据库初始化失败")
    }

    fn sample_design() -> NewBakeDesign {
        NewBakeDesign {
            name: "技术方案结构版".to_string(),
            category: "技术方案".to_string(),
            status: "draft".to_string(),
            tags: r#"[\"方案\"]"#.to_string(),
            applicable_tasks: r#"[\"creation\"]"#.to_string(),
            source_memory_ids: r#"[\"1\"]"#.to_string(),
            source_capture_ids: r#"[\"11\"]"#.to_string(),
            source_episode_ids: r#"[\"ep-1\"]"#.to_string(),
            linked_knowledge_ids: r#"[\"1\",\"2\"]"#.to_string(),
            structure_sections: r#"[{\"title\":\"背景\",\"keywords\":[\"现状\"]}]"#.to_string(),
            style_phrases: r#"[\"整体看\"]"#.to_string(),
            replacement_rules: r#"[{\"from\":\"综上\",\"to\":\"整体看\"}]"#.to_string(),
            prompt_hint: Some("优先输出结构化方案".to_string()),
            detailed_content: Some("## 模板价值\n用于技术方案写作。".to_string()),
            diagram_code: None,
            image_assets: "[]".to_string(),
            usage_count: 0,
            match_score: Some(0.82),
            match_level: Some("high".to_string()),
            creation_mode: "auto".to_string(),
            review_status: "auto_created".to_string(),
            evidence_summary: Some("多次出现稳定结构".to_string()),
            generation_version: Some("bake-v1".to_string()),
            deleted_at: None,
        }
    }

    #[test]
    fn test_insert_and_get_bake_design() {
        let mgr = make_mgr();
        let id = mgr.insert_bake_design(&sample_design()).unwrap();
        let design = mgr.get_bake_design(id).unwrap().unwrap();
        assert_eq!(design.name, "技术方案结构版");
        assert_eq!(design.category, "技术方案");
        assert_eq!(design.creation_mode, "auto");
        assert_eq!(design.review_status, "auto_created");
    }

    #[test]
    fn test_update_bake_design() {
        let mgr = make_mgr();
        let id = mgr.insert_bake_design(&sample_design()).unwrap();
        let mut updated = sample_design();
        updated.name = "周报模板".to_string();
        updated.status = "enabled".to_string();
        updated.review_status = "accepted".to_string();
        assert!(mgr.update_bake_design(id, &updated).unwrap());
        let design = mgr.get_bake_design(id).unwrap().unwrap();
        assert_eq!(design.name, "周报模板");
        assert_eq!(design.status, "enabled");
        assert_eq!(design.review_status, "accepted");
    }

    #[test]
    fn test_toggle_bake_design_status() {
        let mgr = make_mgr();
        let id = mgr.insert_bake_design(&sample_design()).unwrap();
        let toggled = mgr.toggle_bake_design_status(id).unwrap().unwrap();
        assert_eq!(toggled.status, "enabled");
    }
}
