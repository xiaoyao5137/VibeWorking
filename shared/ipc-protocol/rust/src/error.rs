//! IPC 错误类型定义

use thiserror::Error;

#[derive(Debug, Error)]
pub enum IpcError {
    #[error("IO 错误: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON 序列化/反序列化失败: {0}")]
    Json(#[from] serde_json::Error),

    #[error("消息体超过最大长度限制 ({size} > {max} bytes)")]
    MessageTooLarge { size: usize, max: usize },

    #[error("连接未建立或已断开")]
    NotConnected,

    #[error("等待 Sidecar 就绪超时（{seconds}s）")]
    SidecarTimeout { seconds: u64 },

    #[error("Sidecar 返回错误: {0}")]
    SidecarError(String),

    #[error("请求 ID 不匹配（期望 {expected}，实际 {actual}）")]
    IdMismatch { expected: String, actual: String },
}
