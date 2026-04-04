//! 调试相关的 HTTP 处理器
//!
//! 提供：
//! - GET /api/vector/status - 向量化状态
//! - GET /api/stats - 系统统计信息

use std::sync::Arc;

use axum::{extract::State, http::StatusCode, Json};
use serde::{Deserialize, Serialize};

use crate::api::{error::ApiError, state::AppState};

// ─────────────────────────────────────────────────────────────────────────────
// 向量化状态
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct VectorStatusItem {
    pub capture_id: i64,
    pub vectorized: bool,
    pub point_id:   Option<String>,
}

#[derive(Debug, Serialize)]
pub struct VectorStatusResponse {
    pub items: Vec<VectorStatusItem>,
}

/// GET /api/vector/status
///
/// 返回最近 50 条采集记录的向量化状态。
pub async fn vector_status(
    State(state): State<Arc<AppState>>,
) -> Result<Json<VectorStatusResponse>, ApiError> {
    let storage = &state.storage;

    // 获取最近 50 条采集记录
    let captures = storage
        .list(50, 0)
        .map_err(|e| ApiError::Internal(e.to_string()))?;

    let mut items = Vec::new();

    for cap in captures {
        // 查询该 capture_id 是否已向量化
        let vector_record = storage
            .get_by_capture_id(cap.id)
            .ok();

        items.push(VectorStatusItem {
            capture_id: cap.id,
            vectorized: vector_record.is_some(),
            point_id:   vector_record.and_then(|v| Some(v.qdrant_point_id)),
        });
    }

    Ok(Json(VectorStatusResponse { items }))
}

// ─────────────────────────────────────────────────────────────────────────────
// 系统统计
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct SystemStatsResponse {
    pub total_captures:   i64,
    pub total_vectorized: i64,
    pub db_size_mb:       f64,
    pub last_capture_ts:  Option<i64>,
}

/// GET /api/stats
///
/// 返回系统统计信息。
pub async fn system_stats(
    State(state): State<Arc<AppState>>,
) -> Result<Json<SystemStatsResponse>, ApiError> {
    let storage = &state.storage;

    // 统计总采集数
    let total_captures = storage
        .count()
        .map_err(|e| ApiError::Internal(e.to_string()))?;

    // 统计已向量化数量
    let total_vectorized = storage
        .count_vectorized()
        .map_err(|e| ApiError::Internal(e.to_string()))?;

    // 获取最后一条采集记录的时间戳
    let last_capture = storage
        .list(1, 0)
        .ok()
        .and_then(|caps| caps.first().map(|c| c.ts));

    // 获取数据库文件大小
    let db_path = storage.db_path();
    let db_size_mb = std::fs::metadata(&db_path)
        .map(|m| m.len() as f64 / 1024.0 / 1024.0)
        .unwrap_or(0.0);

    Ok(Json(SystemStatsResponse {
        total_captures,
        total_vectorized,
        db_size_mb,
        last_capture_ts: last_capture,
    }))
}

// ─────────────────────────────────────────────────────────────────────────────
// 清空提炼队列
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct ClearExtractionQueueResponse {
    pub cleared: i64,
}

/// POST /api/debug/clear-extraction-queue
///
/// 在 knowledge_entries 插入一条占位记录，然后将所有 knowledge_id IS NULL 的
/// capture 指向该占位记录，从而跳过知识提炼处理。
pub async fn clear_extraction_queue(
    State(state): State<Arc<AppState>>,
) -> Result<Json<ClearExtractionQueueResponse>, ApiError> {
    let cleared = state.storage
        .with_conn_async(|conn| {
            // 1. 找一个待处理 capture 的 id 用于满足外键约束
            let first_capture_id: Option<i64> = conn.query_row(
                "SELECT id FROM captures WHERE knowledge_id IS NULL LIMIT 1",
                [],
                |r| r.get(0),
            ).ok();

            let Some(capture_id) = first_capture_id else {
                return Ok(0i64); // 队列为空
            };

            // 2. 插入占位 knowledge_entry
            conn.execute(
                "INSERT INTO knowledge_entries (capture_id, summary, overview, importance, is_self_generated)
                 VALUES (?, '[SKIPPED]', '队列清空占位记录', 0, 1)",
                rusqlite::params![capture_id],
            ).map_err(|e| crate::storage::StorageError::Sqlite(e))?;

            let skip_id = conn.last_insert_rowid();

            // 3. 批量将待处理 captures 指向该占位记录
            let n = conn.execute(
                "UPDATE captures SET knowledge_id = ? WHERE knowledge_id IS NULL",
                rusqlite::params![skip_id],
            ).map_err(|e| crate::storage::StorageError::Sqlite(e))?;

            Ok(n as i64)
        })
        .await
        .map_err(|e| ApiError::Internal(e.to_string()))?;

    Ok(Json(ClearExtractionQueueResponse { cleared }))
}
