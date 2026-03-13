//! REST API 模块（axum，localhost:7070）
//!
//! 提供供 UI、MCP 工具调用的统一 HTTP 接口。
//!
//! # 端点概览
//! ```text
//! GET  /health                      健康检查
//! GET  /captures?from=&to=&app=&q=  查询采集记录
//! POST /query                       RAG 语义查询（stub）
//! POST /action/execute              键鼠指令执行（stub）
//! GET  /preferences                 获取用户偏好
//! PUT  /preferences/:key            更新用户偏好
//! POST /pii/scrub                   PII 脱敏（stub）
//! ```

pub mod error;
pub mod handlers;
pub mod server;
pub mod state;

pub use server::create_router;
pub use server::start_server;
pub use state::AppState;
