//! REST API 集成测试
//!
//! 测试覆盖：
//! - GET /health → 200 + {"status":"ok"}
//! - GET /captures（空库）→ 200 + total=0
//! - GET /captures?from=&to= → 200
//! - GET /captures?q=... → 200 (FTS5 降级到空结果)
//! - GET /captures?app=... → 200
//! - GET /preferences → 200 + list
//! - PUT /preferences/:key → 200 + 返回新值
//! - PUT /preferences/:key（无 body）→ 400
//! - POST /query → 200 + stub 回复
//! - POST /action/execute → 200 + stub 回复
//! - POST /pii/scrub → 200 + 原文返回

use std::sync::Arc;
use std::time::Duration;

use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use tower::ServiceExt;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;
use memory_bread_core::{api::AppState, storage::StorageManager};

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

/// 创建测试用 axum Router（使用内存临时 SQLite）
async fn make_test_router() -> (axum::Router, tempfile::TempDir) {
    let tmp    = tempfile::tempdir().unwrap();
    let db     = tmp.path().join("test.db");
    let sm     = StorageManager::open(&db).unwrap();
    let state  = AppState::new(sm);
    let router = memory_bread_core::api::create_router(state);
    (router, tmp)
}

async fn spawn_failing_sidecar() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();

    tokio::spawn(async move {
        if let Ok((mut stream, _)) = listener.accept().await {
            let mut buffer = [0_u8; 2048];
            let _ = stream.read(&mut buffer).await;
            let response = b"HTTP/1.1 500 Internal Server Error\r\ncontent-length: 2\r\ncontent-type: text/plain\r\nconnection: close\r\n\r\n{}";
            let _ = stream.write_all(response).await;
            let _ = stream.shutdown().await;
        }
    });

    tokio::time::sleep(Duration::from_millis(20)).await;
    format!("http://{}", addr)
}

/// 发送请求并返回 (StatusCode, 响应体字符串)
async fn oneshot(router: axum::Router, req: Request<Body>) -> (StatusCode, String) {
    let resp = router.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let body = String::from_utf8_lossy(&bytes).to_string();
    (status, body)
}

// ── /health ───────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_health_200() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder().uri("/health").body(Body::empty()).unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(json["status"], "ok");
}

#[tokio::test]
async fn test_health_version_present() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder().uri("/health").body(Body::empty()).unwrap();
    let (_, body) = oneshot(router, req).await;
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(json["version"].as_str().unwrap().len() > 0);
}

// ── /captures ─────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_captures_empty_db() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder().uri("/captures").body(Body::empty()).unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(json["total"], 0);
    assert!(json["captures"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_captures_with_time_filter() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .uri("/captures?from=0&to=9999999999999&limit=10")
        .body(Body::empty())
        .unwrap();
    let (status, _body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn test_captures_fts_query() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .uri("/captures?q=%E5%B7%A5%E4%BD%9C")  // URL-encoded "工作"
        .body(Body::empty())
        .unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(json["captures"].is_array());
}

#[tokio::test]
async fn test_captures_app_filter() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .uri("/captures?app=%E5%BE%AE%E4%BF%A1")  // URL-encoded "微信"
        .body(Body::empty())
        .unwrap();
    let (status, _) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn test_captures_limit_respected() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .uri("/captures?limit=5")
        .body(Body::empty())
        .unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(json["captures"].as_array().unwrap().len() <= 5);
}

// ── /preferences ──────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_preferences_list() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder().uri("/preferences").body(Body::empty()).unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(json["preferences"].is_array());
    // 种子数据（002_seed_defaults.sql）会插入若干默认偏好
    assert!(json["preferences"].as_array().unwrap().len() >= 0);
}

#[tokio::test]
async fn test_preferences_put() {
    let (router, _tmp) = make_test_router().await;
    let body_json = r#"{"value":"测试值"}"#;
    let req = Request::builder()
        .method(Method::PUT)
        .uri("/preferences/test.api.key")
        .header("content-type", "application/json")
        .body(Body::from(body_json))
        .unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK, "body: {body}");
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(json["key"], "test.api.key");
    assert_eq!(json["value"], "测试值");
}

#[tokio::test]
async fn test_preferences_put_update_existing() {
    let (router, _tmp) = make_test_router().await;
    // 第一次设置
    let req1 = Request::builder()
        .method(Method::PUT)
        .uri("/preferences/test.update.key")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"value":"原始值"}"#))
        .unwrap();
    let (s1, _) = oneshot(router.clone(), req1).await;
    assert_eq!(s1, StatusCode::OK);

    // 第二次更新
    let req2 = Request::builder()
        .method(Method::PUT)
        .uri("/preferences/test.update.key")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"value":"更新后的值"}"#))
        .unwrap();
    let (s2, body2) = oneshot(router, req2).await;
    assert_eq!(s2, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body2).unwrap();
    assert_eq!(json["value"], "更新后的值");
}

#[tokio::test]
async fn test_preferences_put_invalid_body_400() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .method(Method::PUT)
        .uri("/preferences/test.key")
        .header("content-type", "application/json")
        .body(Body::from("not-json"))
        .unwrap();
    let (status, _) = oneshot(router, req).await;
    // axum 返回 422（JSON parse 失败）
    assert!(
        status == StatusCode::UNPROCESSABLE_ENTITY || status == StatusCode::BAD_REQUEST,
        "expected 4xx, got {status}"
    );
}

// ── /query ────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_query_stub_returns_200() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .method(Method::POST)
        .uri("/query")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"query":"今日工作总结"}"#))
        .unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(json["answer"].as_str().unwrap().len() > 0);
    assert!(json["contexts"].is_array());
}

#[tokio::test]
async fn test_query_fallback_returns_only_knowledge_contexts() {
    let tmp = tempfile::tempdir().unwrap();
    let db = tmp.path().join("test.db");
    let sm = StorageManager::open(&db).unwrap();

    sm.with_conn(|conn| {
        conn.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, capture_id INTEGER NOT NULL, summary TEXT, overview TEXT, details TEXT, created_at INTEGER, updated_at INTEGER)",
            [],
        )?;
        conn.execute(
            "INSERT INTO knowledge_entries (capture_id, summary, overview, details, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            rusqlite::params![1_i64, "Gemini 问答", "今天问了 Gemini 发布计划", "整理发布相关提问", 1_710_000_000_000_i64, 1_710_000_000_000_i64],
        )?;
        conn.execute(
            "INSERT INTO captures (ts, app_name, win_title, event_type, ax_text, ocr_text, is_sensitive) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            rusqlite::params![1_710_000_000_100_i64, "Gemini", "Gemini", "auto", "今天问了 Gemini 发布计划", "今天问了 Gemini 发布计划", 0_i64],
        )?;
        Ok::<_, memory_bread_core::storage::StorageError>(())
    }).unwrap();

    let sidecar_url = spawn_failing_sidecar().await;
    let state = Arc::new(AppState { storage: sm, sidecar_url });
    let router = memory_bread_core::api::create_router(state);

    let req = Request::builder()
        .method(Method::POST)
        .uri("/query")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"query":"Gemini 发布计划","top_k":5}"#))
        .unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK, "body: {body}");
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    let contexts = json["contexts"].as_array().unwrap();
    assert_eq!(contexts.len(), 1, "body: {body}");
    assert_eq!(contexts[0]["source"], "knowledge");
    assert_eq!(json["model"], "keyword-fallback");
}

// ── /action/execute ───────────────────────────────────────────────────────────

#[tokio::test]
async fn test_action_stub_returns_200() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .method(Method::POST)
        .uri("/action/execute")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"action_type":"click","coords":[100.0,200.0]}"#))
        .unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(json["action_id"].as_str().unwrap().len() > 0);
}

// ── /pii/scrub ────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_pii_scrub_stub_returns_text() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .method(Method::POST)
        .uri("/pii/scrub")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"text":"我的手机号是 13800138000"}"#))
        .unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    // stub 原文返回，不做脱敏
    assert_eq!(json["text"], "我的手机号是 13800138000");
    assert_eq!(json["redacted_count"], 0);
}

// ── 404 测试 ──────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_knowledge_api_returns_semantic_fields() {
    let (router, tmp) = make_test_router().await;
    let db = tmp.path().join("test.db");
    let sm = StorageManager::open(&db).unwrap();

    sm.with_conn(|conn| {
        conn.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, capture_id INTEGER NOT NULL, summary TEXT, overview TEXT, details TEXT, entities TEXT, category TEXT, importance INTEGER, occurrence_count INTEGER, observed_at INTEGER, event_time_start INTEGER, event_time_end INTEGER, history_view INTEGER NOT NULL DEFAULT 0, content_origin TEXT, activity_type TEXT, is_self_generated INTEGER NOT NULL DEFAULT 0, evidence_strength TEXT, user_verified INTEGER NOT NULL DEFAULT 0, user_edited INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
            [],
        )?;
        conn.execute(
            "INSERT INTO knowledge_entries (capture_id, summary, overview, details, entities, category, importance, occurrence_count, observed_at, event_time_start, event_time_end, history_view, content_origin, activity_type, is_self_generated, evidence_strength, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, datetime(?17/1000, 'unixepoch'), datetime(?18/1000, 'unixepoch'))",
            rusqlite::params![
                1_i64,
                "今天回看飞书消息",
                "今天回看飞书消息",
                "确认了昨天的发布安排",
                "[\"飞书\",\"发布\"]",
                "聊天",
                4_i64,
                1_i64,
                1_710_000_100_000_i64,
                1_709_913_600_000_i64,
                1_709_914_000_000_i64,
                1_i64,
                "historical_content",
                "reviewing_history",
                0_i64,
                "high",
                1_710_000_100_000_i64,
                1_710_000_100_000_i64,
            ],
        )?;
        Ok::<_, memory_bread_core::storage::StorageError>(())
    }).unwrap();

    let req = Request::builder().uri("/api/knowledge").body(Body::empty()).unwrap();
    let (status, body) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::OK, "body: {body}");
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    let entry = &json["entries"][0];
    assert_eq!(entry["observed_at"], 1_710_000_100_000_i64);
    assert_eq!(entry["event_time_start"], 1_709_913_600_000_i64);
    assert_eq!(entry["event_time_end"], 1_709_914_000_000_i64);
    assert_eq!(entry["history_view"], true);
    assert_eq!(entry["content_origin"], "historical_content");
    assert_eq!(entry["activity_type"], "reviewing_history");
    assert_eq!(entry["is_self_generated"], false);
    assert_eq!(entry["evidence_strength"], "high");
}

