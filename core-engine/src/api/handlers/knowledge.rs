//! 知识库 API 处理器
//!
//! 提供知识条目的查询、验证、删除等功能

use std::sync::Arc;

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};

use crate::api::{error::ApiError, state::AppState};

/// 知识条目
#[derive(Debug, Serialize, Deserialize)]
pub struct KnowledgeEntry {
    pub id: i64,
    pub capture_id: i64,
    pub summary: String,
    pub overview: Option<String>,
    pub details: Option<String>,
    pub entities: Vec<String>,
    pub category: String,
    pub importance: i64,
    pub occurrence_count: Option<i64>,
    pub user_verified: bool,
    pub user_edited: bool,
    pub created_at: String,
    pub updated_at: String,
}

/// 查询参数
#[derive(Debug, Deserialize)]
pub struct KnowledgeQuery {
    #[serde(default = "default_limit")]
    pub limit: i64,
    #[serde(default)]
    pub offset: i64,
    pub category: Option<String>,
}

fn default_limit() -> i64 {
    50
}

/// 知识条目列表响应
#[derive(Debug, Serialize)]
pub struct KnowledgeListResponse {
    pub entries: Vec<KnowledgeEntry>,
    pub total: i64,
}

/// GET /api/knowledge - 获取知识条目列表
pub async fn list_knowledge(
    State(state): State<Arc<AppState>>,
    Query(params): Query<KnowledgeQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let result = state.storage.with_conn_async(move |conn| {
        // 参数化查询，避免 SQL 注入
        let (entries, total) = if let Some(ref category) = params.category {
            let mut stmt = conn.prepare(
                "SELECT id, capture_id, summary, overview, details, entities, category, importance,
                 occurrence_count, user_verified, user_edited, created_at, updated_at
                 FROM knowledge_entries WHERE category = ?1
                 ORDER BY created_at DESC LIMIT ?2 OFFSET ?3"
            ).map_err(|e| crate::storage::StorageError::Rusqlite(e))?;

            let entries = stmt
                .query_map(rusqlite::params![category, params.limit, params.offset], |row| {
                    let entities_json: String = row.get(5).unwrap_or_default();
                    let entities: Vec<String> = serde_json::from_str(&entities_json).unwrap_or_default();
                    Ok(KnowledgeEntry {
                        id: row.get(0)?, capture_id: row.get(1)?,
                        summary: row.get(2)?, overview: row.get(3).ok(),
                        details: row.get(4).ok(), entities,
                        category: row.get(6)?, importance: row.get(7)?,
                        occurrence_count: row.get(8).ok(),
                        user_verified: row.get(9)?, user_edited: row.get(10)?,
                        created_at: row.get(11)?, updated_at: row.get(12)?,
                    })
                })
                .map_err(|e| crate::storage::StorageError::Rusqlite(e))?
                .collect::<Result<Vec<_>, _>>()
                .map_err(|e| crate::storage::StorageError::Rusqlite(e))?;

            let total: i64 = conn
                .query_row(
                    "SELECT COUNT(*) FROM knowledge_entries WHERE category = ?1",
                    rusqlite::params![category],
                    |row| row.get(0),
                )
                .map_err(|e| crate::storage::StorageError::Rusqlite(e))?;

            (entries, total)
        } else {
            let mut stmt = conn.prepare(
                "SELECT id, capture_id, summary, overview, details, entities, category, importance,
                 occurrence_count, user_verified, user_edited, created_at, updated_at
                 FROM knowledge_entries
                 ORDER BY created_at DESC LIMIT ?1 OFFSET ?2"
            ).map_err(|e| crate::storage::StorageError::Rusqlite(e))?;

            let entries = stmt
                .query_map(rusqlite::params![params.limit, params.offset], |row| {
                    let entities_json: String = row.get(5).unwrap_or_default();
                    let entities: Vec<String> = serde_json::from_str(&entities_json).unwrap_or_default();
                    Ok(KnowledgeEntry {
                        id: row.get(0)?, capture_id: row.get(1)?,
                        summary: row.get(2)?, overview: row.get(3).ok(),
                        details: row.get(4).ok(), entities,
                        category: row.get(6)?, importance: row.get(7)?,
                        occurrence_count: row.get(8).ok(),
                        user_verified: row.get(9)?, user_edited: row.get(10)?,
                        created_at: row.get(11)?, updated_at: row.get(12)?,
                    })
                })
                .map_err(|e| crate::storage::StorageError::Rusqlite(e))?
                .collect::<Result<Vec<_>, _>>()
                .map_err(|e| crate::storage::StorageError::Rusqlite(e))?;

            let total: i64 = conn
                .query_row("SELECT COUNT(*) FROM knowledge_entries", [], |row| row.get(0))
                .map_err(|e| crate::storage::StorageError::Rusqlite(e))?;

            (entries, total)
        };

        Ok(KnowledgeListResponse { entries, total })
    }).await?;

    Ok(Json(result))
}

/// POST /api/knowledge/:id/verify - 验证知识条目
pub async fn verify_knowledge(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> Result<impl IntoResponse, ApiError> {
    state.storage.with_conn_async(move |conn| {
        conn.execute(
            "UPDATE knowledge_entries SET user_verified = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [id],
        ).map_err(|e| crate::storage::StorageError::Rusqlite(e))?;
        Ok(())
    }).await?;
    Ok(StatusCode::OK)
}

/// DELETE /api/knowledge/:id - 删除知识条目
pub async fn delete_knowledge(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> Result<impl IntoResponse, ApiError> {
    state.storage.with_conn_async(move |conn| {
        conn.execute("DELETE FROM knowledge_entries WHERE id = ?", [id])
            .map_err(|e| crate::storage::StorageError::Rusqlite(e))?;
        Ok(())
    }).await?;
    Ok(StatusCode::OK)
}
