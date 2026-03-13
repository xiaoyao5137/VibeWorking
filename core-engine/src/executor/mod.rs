//! 键鼠自动化执行器（Automation Executor）
//!
//! 通过 `enigo` crate 模拟键盘和鼠标操作。
//!
//! # 设计原则
//! - **半自动模式**（默认）：每次执行前向 UI 发送确认请求
//! - **全自动模式**：用户显式开启后，跳过确认直接执行
//! - 所有操作记录到 `action_logs` 表（通过 StorageManager）
//! - 失败不 panic，通过 `ExecutorError` 向上传递

pub mod action;
pub mod error;
pub mod executor;

pub use action::{ActionCommand, ActionResult};
pub use error::ExecutorError;
pub use executor::AutomationExecutor;
