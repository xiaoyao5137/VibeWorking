//! 共享应用状态（通过 axum State extractor 注入每个 handler）

use std::sync::Arc;

use crate::storage::StorageManager;

/// 所有 Handler 共享的应用状态。
///
/// 使用 `Arc<AppState>` 确保零拷贝跨线程共享。
#[derive(Clone)]
pub struct AppState {
    pub storage: StorageManager,
}

impl AppState {
    pub fn new(storage: StorageManager) -> Arc<Self> {
        Arc::new(Self { storage })
    }
}
