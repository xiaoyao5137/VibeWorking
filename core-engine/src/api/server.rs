//! axum Router 组装与服务启动

use std::sync::Arc;

use axum::{
    routing::{get, post, put},
    Router,
};
use tower_http::cors::{Any, CorsLayer};
use tracing::info;

use super::{
    handlers::{
        action::execute_action,
        captures::list_captures,
        debug::{system_stats, vector_status},
        health::health_handler,
        knowledge::{delete_knowledge, list_knowledge, verify_knowledge},
        pii::pii_scrub,
        preferences::{list_preferences, update_preference},
        query::rag_query,
    },
    state::AppState,
};

/// 构造 axum Router（不启动监听）。
///
/// 测试中直接使用此函数构造 router，无需真实 TCP 端口。
pub fn create_router(state: Arc<AppState>) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    Router::new()
        .route("/health",                get(health_handler))
        .route("/api/captures",          get(list_captures))
        .route("/captures",              get(list_captures))
        .route("/query",                 post(rag_query))
        .route("/action/execute",        post(execute_action))
        .route("/preferences",           get(list_preferences))
        .route("/preferences/:key",      put(update_preference))
        .route("/pii/scrub",             post(pii_scrub))
        .route("/api/vector/status",     get(vector_status))
        .route("/api/stats",             get(system_stats))
        .route("/api/knowledge",         get(list_knowledge))
        .route("/api/knowledge/:id/verify", post(verify_knowledge))
        .route("/api/knowledge/:id",     axum::routing::delete(delete_knowledge))
        .layer(cors)
        .with_state(state)
}

/// 启动 HTTP 服务器（绑定到 addr，阻塞直到关闭）。
///
/// `addr` 默认为 `"127.0.0.1:7070"`。
pub async fn start_server(
    state: Arc<AppState>,
    addr:  &str,
) -> anyhow::Result<()> {
    let app      = create_router(state);
    let listener = tokio::net::TcpListener::bind(addr).await?;
    info!("WorkBuddy API 服务已启动，监听地址: http://{addr}");
    axum::serve(listener, app).await?;
    Ok(())
}
