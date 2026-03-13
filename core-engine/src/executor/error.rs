//! executor 层统一错误类型

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ExecutorError {
    #[error("平台不支持: {0}")]
    UnsupportedPlatform(String),

    #[error("权限不足（需要辅助功能权限）: {0}")]
    PermissionDenied(String),

    #[error("目标元素未找到: {0}")]
    TargetNotFound(String),

    #[error("执行被用户取消")]
    Cancelled,

    #[error("执行超时（{0}ms）")]
    Timeout(u64),

    #[error("动作类型不支持: {0}")]
    UnsupportedAction(String),

    #[error("全自动模式未开启（当前为半自动模式，需要用户确认）")]
    RequiresConfirmation,

    #[error("底层驱动错误: {0}")]
    DriverError(String),

    #[error("存储错误: {0}")]
    Storage(#[from] crate::storage::StorageError),
}
