//! storage 模块公开 API
//!
//! 外部代码只需：
//! ```rust
//! use workbuddy_core::storage::{StorageManager, models::*, error::StorageError};
//! ```

pub mod cleanup;
pub mod db;
pub mod error;
pub mod models;
pub mod repo;

pub use db::StorageManager;
pub use error::StorageError;
