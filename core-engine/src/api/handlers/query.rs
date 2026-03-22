//! POST /query — RAG 语义查询
//!
//! 通过 HTTP 调用 ai-sidecar 的 RAG 服务进行智能问答

use std::sync::Arc;
use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use crate::api::{error::ApiError, state::AppState};

const FALLBACK_NOISE_OVERVIEW_PREFIX: &str = "低价值工作片段（";

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

    // 调用 ai-sidecar 的 RAG 服务
    let client = reqwest::Client::new();
    let rag_service_url = format!("{}/query", state.sidecar_url);

    let request_body = serde_json::json!({
        "query": query,
        "top_k": top_k,
    });

    match client
        .post(&rag_service_url)
        .json(&request_body)
        .timeout(std::time::Duration::from_secs(120))  // 增加超时到 120 秒
        .send()
        .await
    {
        Ok(response) => {
            if response.status().is_success() {
                match response.json::<RagQueryResponse>().await {
                    Ok(rag_response) => Ok(Json(rag_response)),
                    Err(e) => Err(ApiError::Internal(format!("解析 RAG 响应失败: {}", e))),
                }
            } else {
                // RAG 服务返回错误，降级为简单的关键词搜索
                tracing::warn!("RAG 服务返回错误，降级为关键词搜索");
                fallback_keyword_search(query, top_k, state).await
            }
        }
        Err(e) => {
            // 无法连接到 RAG 服务，降级为简单的关键词搜索
            tracing::warn!("无法连接到 RAG 服务: {}，降级为关键词搜索", e);
            fallback_keyword_search(query, top_k, state).await
        }
    }
}

/// 降级方案：使用简单的关键词搜索
async fn fallback_keyword_search(
    query: String,
    top_k: usize,
    state: Arc<AppState>,
) -> Result<Json<RagQueryResponse>, ApiError> {
    let result = state.storage.with_conn_async(move |conn| {
        let mut contexts = Vec::new();
        let search_pattern = format!("%{}%", query);

        // 从知识库检索
        let knowledge_query = "SELECT id, capture_id, overview, details, summary
             FROM knowledge_entries
             WHERE (overview LIKE ? OR details LIKE ? OR summary LIKE ?)
               AND summary NOT LIKE ?
             ORDER BY created_at DESC
             LIMIT ?";

        if let Ok(mut stmt) = conn.prepare(knowledge_query) {
            if let Ok(rows) = stmt.query_map(
                [
                    &search_pattern,
                    &search_pattern,
                    &search_pattern,
                    &format!("{}%", FALLBACK_NOISE_OVERVIEW_PREFIX),
                    &top_k.to_string(),
                ],
                |row| {
                    let overview: Option<String> = row.get(2).ok();
                    let details: Option<String> = row.get(3).ok();
                    let summary: String = row.get(4).unwrap_or_default();

                    let text = if let Some(ov) = overview {
                        if let Some(det) = details {
                            format!("{}\n详细内容：{}", ov, det)
                        } else {
                            ov
                        }
                    } else {
                        summary
                    };

                    Ok(RagContext {
                        capture_id: row.get(1)?,
                        text,
                        score: 1.0,
                        source: "knowledge".to_string(),
                    })
                },
            ) {
                for row in rows.flatten() {
                    contexts.push(row);
                }
            }
        }

        // 如果知识库结果不足，从采集记录补充
        if contexts.len() < top_k {
            let remaining = top_k - contexts.len();
            let capture_query = "SELECT id, ocr_text, ax_text
                 FROM captures
                 WHERE ocr_text LIKE ? OR ax_text LIKE ?
                 ORDER BY ts DESC
                 LIMIT ?";

            if let Ok(mut stmt) = conn.prepare(capture_query) {
                if let Ok(rows) = stmt.query_map(
                    [&search_pattern, &search_pattern, &remaining.to_string()],
                    |row| {
                        let ocr_text: Option<String> = row.get(1).ok();
                        let ax_text: Option<String> = row.get(2).ok();

                        let text = ocr_text
                            .or(ax_text)
                            .unwrap_or_default()
                            .chars()
                            .take(500)
                            .collect::<String>();

                        Ok(RagContext {
                            capture_id: row.get(0)?,
                            text,
                            score: 1.0,
                            source: "capture".to_string(),
                        })
                    },
                ) {
                    for row in rows.flatten() {
                        contexts.push(row);
                    }
                }
            }
        }

        let answer = if contexts.is_empty() {
            format!("抱歉，我在工作记录中没有找到与「{}」相关的信息。", query)
        } else {
            let context_summary: Vec<String> = contexts
                .iter()
                .take(3)
                .map(|c| {
                    let preview = c.text.chars().take(100).collect::<String>();
                    format!("• {}", preview)
                })
                .collect();

            format!(
                "根据工作记录，我找到了 {} 条相关信息：\n\n{}\n\n提示：RAG 服务暂时不可用，这是基于关键词检索的降级结果。",
                contexts.len(),
                context_summary.join("\n")
            )
        };

        Ok::<_, crate::storage::StorageError>(RagQueryResponse {
            answer,
            contexts,
            model: "keyword-fallback".to_string(),
        })
    }).await?;

    Ok(Json(result))
}
