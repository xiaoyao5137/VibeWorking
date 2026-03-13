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
    let storage = state.storage.clone();

    tokio::task::spawn_blocking(move || {
        let conn = storage.conn.lock().map_err(|e| {
            ApiError::Internal(format!("获取数据库连接失败: {}", e))
        })?;

        // 构建查询
        let mut query = String::from(
            "SELECT id, capture_id, summary, overview, details, entities, category, importance,
             occurrence_count, user_verified, user_edited, created_at, updated_at
             FROM knowledge_entries WHERE 1=1"
        );

        if let Some(ref category) = params.category {
            query.push_str(&format!(" AND category = '{}'", category));
        }

        query.push_str(" ORDER BY created_at DESC");
        query.push_str(&format!(" LIMIT {} OFFSET {}", params.limit, params.offset));

        // 执行查询
        let mut stmt = conn.prepare(&query).map_err(|e| {
            ApiError::Internal(format!("准备查询失败: {}", e))
        })?;

        let entries = stmt
            .query_map([], |row| {
                let entities_json: String = row.get(5).unwrap_or_default();
                let entities: Vec<String> = serde_json::from_str(&entities_json).unwrap_or_default();

                Ok(KnowledgeEntry {
                    id: row.get(0)?,
                    capture_id: row.get(1)?,
                    summary: row.get(2)?,
                    overview: row.get(3).ok(),
                    details: row.get(4).ok(),
                    entities,
                    category: row.get(6)?,
                    importance: row.get(7)?,
                    occurrence_count: row.get(8).ok(),
                    user_verified: row.get(9)?,
                    user_edited: row.get(10)?,
                    created_at: row.get(11)?,
                    updated_at: row.get(12)?,
                })
            })
            .map_err(|e| ApiError::Internal(format!("查询失败: {}", e)))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| ApiError::Internal(format!("解析结果失败: {}", e)))?;

        // 获取总数
        let total_query = if let Some(ref category) = params.category {
            format!("SELECT COUNT(*) FROM knowledge_entries WHERE category = '{}'", category)
        } else {
            "SELECT COUNT(*) FROM knowledge_entries".to_string()
        };

        let total: i64 = conn
            .query_row(&total_query, [], |row| row.get(0))
            .map_err(|e| ApiError::Internal(format!("获取总数失败: {}", e)))?;

        Ok::<_, ApiError>(Json(KnowledgeListResponse { entries, total }))
    })
    .await
    .map_err(|e| ApiError::Internal(format!("任务执行失败: {}", e)))?
}

/// POST /api/knowledge/:id/verify - 验证知识条目
pub async fn verify_knowledge(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> Result<impl IntoResponse, ApiError> {
    let storage = state.storage.clone();

    tokio::task::spawn_blocking(move || {
        let conn = storage.conn.lock().map_err(|e| {
            ApiError::Internal(format!("获取数据库连接失败: {}", e))
        })?;

        conn.execute(
            "UPDATE knowledge_entries SET user_verified = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [id],
        )
        .map_err(|e| ApiError::Internal(format!("更新失败: {}", e)))?;

        Ok::<_, ApiError>(StatusCode::OK)
    })
    .await
    .map_err(|e| ApiError::Internal(format!("任务执行失败: {}", e)))?
}

/// DELETE /api/knowledge/:id - 删除知识条目
pub async fn delete_knowledge(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> Result<impl IntoResponse, ApiError> {
    let storage = state.storage.clone();

    tokio::task::spawn_blocking(move || {
        let conn = storage.conn.lock().map_err(|e| {
            ApiError::Internal(format!("获取数据库连接失败: {}", e))
        })?;

        conn.execute("DELETE FROM knowledge_entries WHERE id = ?", [id])
            .map_err(|e| ApiError::Internal(format!("删除失败: {}", e)))?;

        Ok::<_, ApiError>(StatusCode::OK)
    })
    .await
    .map_err(|e| ApiError::Internal(format!("任务执行失败: {}", e)))?
}
