//! 用户画像 API 处理器

use std::sync::Arc;

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};

use crate::{
    api::{error::ApiError, state::AppState},
    storage::models::{NewUserProfile, UserProfileRecord},
};

/// 查询参数
#[derive(Debug, Deserialize)]
pub struct ProfileQuery {
    /// 快照类型: daily/weekly/monthly/yearly
    #[serde(rename = "type")]
    pub snapshot_type: Option<String>,
    /// 限制返回数量
    pub limit: Option<usize>,
}

/// 画像响应
#[derive(Debug, Serialize)]
pub struct ProfileResponse {
    pub id: i64,
    pub snapshot_type: String,
    pub snapshot_date: String,
    pub content: serde_json::Value,
    pub is_system_generated: bool,
    pub created_at: String,
    pub updated_at: String,
}

impl From<UserProfileRecord> for ProfileResponse {
    fn from(record: UserProfileRecord) -> Self {
        let content = serde_json::from_str(&record.content).unwrap_or(serde_json::json!({}));
        Self {
            id: record.id,
            snapshot_type: record.snapshot_type,
            snapshot_date: record.snapshot_date,
            content,
            is_system_generated: record.is_system_generated,
            created_at: record.created_at,
            updated_at: record.updated_at,
        }
    }
}

/// 更新画像请求
#[derive(Debug, Deserialize)]
pub struct UpdateProfileRequest {
    pub content: serde_json::Value,
}

/// GET /api/profiles - 获取画像列表
pub async fn list_profiles(
    State(state): State<Arc<AppState>>,
    Query(query): Query<ProfileQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let limit = query.limit.unwrap_or(50);
    let snapshot_type = query.snapshot_type.as_deref();

    let records = state
        .storage
        .list_user_profiles(snapshot_type, limit)
        .map_err(|e| ApiError::Internal(e.to_string()))?;

    let profiles: Vec<ProfileResponse> = records.into_iter().map(Into::into).collect();

    Ok(Json(profiles))
}

/// GET /api/profiles/:id - 获取单个画像
pub async fn get_profile(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> Result<impl IntoResponse, ApiError> {
    let record = state
        .storage
        .get_user_profile(id)
        .map_err(|e| ApiError::Internal(e.to_string()))?
        .ok_or_else(|| ApiError::NotFound(format!("画像 {} 不存在", id)))?;

    Ok(Json(ProfileResponse::from(record)))
}

/// PUT /api/profiles/:id - 更新画像内容（用户编辑）
pub async fn update_profile(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
    Json(req): Json<UpdateProfileRequest>,
) -> Result<impl IntoResponse, ApiError> {
    let content_str = serde_json::to_string(&req.content)
        .map_err(|e| ApiError::BadRequest(format!("JSON 格式错误: {}", e)))?;

    state
        .storage
        .update_user_profile_content(id, &content_str)
        .map_err(|e| ApiError::Internal(e.to_string()))?;

    Ok(StatusCode::NO_CONTENT)
}

/// GET /api/profiles/latest - 获取最新画像
pub async fn get_latest_profile(
    State(state): State<Arc<AppState>>,
    Query(query): Query<ProfileQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let snapshot_type = query.snapshot_type.as_deref().unwrap_or("daily");

    let record = state
        .storage
        .get_latest_profile(snapshot_type)
        .map_err(|e| ApiError::Internal(e.to_string()))?
        .ok_or_else(|| ApiError::NotFound(format!("暂无 {} 画像", snapshot_type)))?;

    Ok(Json(ProfileResponse::from(record)))
}
