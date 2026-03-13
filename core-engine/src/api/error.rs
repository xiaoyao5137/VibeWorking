//! API 错误类型 → HTTP 响应映射

use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

use crate::storage::StorageError;

#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("storage error: {0}")]
    Storage(#[from] StorageError),

    #[error("not found: {0}")]
    NotFound(String),

    #[error("bad request: {0}")]
    BadRequest(String),

    #[error("internal error: {0}")]
    Internal(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, code, message) = match &self {
            ApiError::NotFound(msg)  => (StatusCode::NOT_FOUND,            "NOT_FOUND",       msg.as_str()),
            ApiError::BadRequest(msg)=> (StatusCode::BAD_REQUEST,          "BAD_REQUEST",     msg.as_str()),
            ApiError::Storage(_)     => (StatusCode::INTERNAL_SERVER_ERROR,"STORAGE_ERROR",   "数据库操作失败"),
            ApiError::Internal(msg)  => (StatusCode::INTERNAL_SERVER_ERROR,"INTERNAL_ERROR",  msg.as_str()),
        };
        (
            status,
            Json(json!({ "error": code, "message": message })),
        )
            .into_response()
    }
}
