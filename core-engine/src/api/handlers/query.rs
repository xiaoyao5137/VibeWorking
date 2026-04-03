//! POST /query — RAG 语义查询
//!
//! 通过 HTTP 调用 ai-sidecar 的 RAG 服务进行智能问答

use std::sync::Arc;
use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use crate::api::{error::ApiError, state::AppState};

#[derive(Deserialize)]
pub struct RagQueryRequest {
    pub query: String,
    #[serde(default = "default_top_k")]
    pub top_k: usize,
}

fn default_top_k() -> usize { 5 }

#[derive(Serialize, Deserialize, Clone)]
pub struct RagContext {
    pub capture_id: i64,
    pub text: String,
    pub score: f64,
    pub source: String,
}

#[derive(Serialize, Deserialize)]
pub struct RagQueryResponse {
    pub answer:   String,
    pub contexts: Vec<RagContext>,
    pub model:    String,
}

/// RAG 查询实现：调用 ai-sidecar 的 RAG 服务
pub async fn rag_query(
    State(state): State<Arc<AppState>>,
    Json(body): Json<RagQueryRequest>,
) -> Result<Json<RagQueryResponse>, ApiError> {
    let query = body.query.clone();
    let top_k = body.top_k;

    let client = reqwest::Client::new();
    let rag_service_url = format!("{}/query", state.sidecar_url);

    let request_body = serde_json::json!({
        "query": query,
        "top_k": top_k,
    });

    let response = client
        .post(&rag_service_url)
        .json(&request_body)
        .timeout(std::time::Duration::from_secs(120))
        .send()
        .await
        .map_err(|e| {
            tracing::warn!("无法连接到 RAG 服务: {}", e);
            ApiError::Internal(format!("RAG 服务不可用，请确认 AI Sidecar 已正常启动: {}", e))
        })?;

    if response.status().is_success() {
        let rag_response = response
            .json::<RagQueryResponse>()
            .await
            .map_err(|e| ApiError::Internal(format!("解析 RAG 响应失败: {}", e)))?;
        Ok(Json(rag_response))
    } else {
        let status = response.status();
        let body_text = response.text().await.unwrap_or_default();
        tracing::warn!("RAG 服务返回错误 status={} body={}", status, body_text);
        Err(ApiError::Internal(format!("RAG 服务返回错误 ({})", status)))
    }
}
