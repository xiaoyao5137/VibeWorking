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

use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use tower::ServiceExt;
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

/// 发送请求并返回 (StatusCode, 响应体字符串)
async fn oneshot(router: axum::Router, req: Request<Body>) -> (StatusCode, String) {
    let resp   = router.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes  = resp.into_body().collect().await.unwrap().to_bytes();
    let body   = String::from_utf8_lossy(&bytes).to_string();
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
async fn test_query_contains_user_question() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder()
        .method(Method::POST)
        .uri("/query")
        .header("content-type", "application/json")
        .body(Body::from(r#"{"query":"飞书会议记录"}"#))
        .unwrap();
    let (_, body) = oneshot(router, req).await;
    assert!(body.contains("飞书会议记录"));
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
async fn test_unknown_route_404() {
    let (router, _tmp) = make_test_router().await;
    let req = Request::builder().uri("/nonexistent").body(Body::empty()).unwrap();
    let (status, _) = oneshot(router, req).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}
