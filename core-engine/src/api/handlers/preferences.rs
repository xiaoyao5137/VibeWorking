//! GET /preferences — 获取所有用户偏好
//! PUT /preferences/:key — 更新单条偏好

use std::sync::Arc;

use axum::{
    extract::{Path, State},
    Json,
};
use serde::{Deserialize, Serialize};

use crate::{
    api::{error::ApiError, state::AppState},
    storage::models::PreferenceRecord,
};

#[derive(Serialize)]
pub struct PreferencesResponse {
    pub preferences: Vec<PreferenceRecord>,
}

pub async fn list_preferences(
    State(state): State<Arc<AppState>>,
) -> Result<Json<PreferencesResponse>, ApiError> {
    let storage = state.storage.clone();
    let prefs = tokio::task::spawn_blocking(move || {
        storage.list_preferences()
    })
    .await
    .map_err(|e| ApiError::Internal(e.to_string()))??;

    Ok(Json(PreferencesResponse { preferences: prefs }))
}

/// PUT /preferences/:key 请求体
#[derive(Deserialize)]
pub struct UpdatePreferenceRequest {
    pub value: String,
}

#[derive(Serialize)]
pub struct UpdatePreferenceResponse {
    pub key:        String,
    pub value:      String,
    pub updated_at: i64,
}

pub async fn update_preference(
    State(state): State<Arc<AppState>>,
    Path(key): Path<String>,
    Json(body): Json<UpdatePreferenceRequest>,
) -> Result<Json<UpdatePreferenceResponse>, ApiError> {
    if key.is_empty() {
        return Err(ApiError::BadRequest("key 不能为空".into()));
    }

    let key_clone   = key.clone();
    let value_clone = body.value.clone();
    let storage     = state.storage.clone();

    let record = tokio::task::spawn_blocking(move || {
        // 用户手动设置：source="user"，confidence=1.0
        storage.upsert_preference(&key_clone, &value_clone, "user", 1.0)?;
        storage
            .get_preference(&key_clone)?
            .ok_or_else(|| crate::storage::StorageError::NotFound(
                format!("preference '{key_clone}' not found after upsert"),
            ))
    })
    .await
    .map_err(|e| ApiError::Internal(e.to_string()))??;

    Ok(Json(UpdatePreferenceResponse {
        key:        record.key,
        value:      record.value,
        updated_at: record.updated_at,
    }))
}
