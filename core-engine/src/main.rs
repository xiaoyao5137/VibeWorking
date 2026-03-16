//! WorkBuddy Core Engine — 二进制入口

use std::path::PathBuf;
use std::sync::Arc;

use tokio::sync::mpsc;
use workbuddy_core::{
    api::{server::start_server, state::AppState},
    capture::{start_listener, CaptureConfig, CaptureEngine, ListenerConfig},
    monitor::ResourceMonitor,
    scheduler::Scheduler,
    storage::StorageManager,
};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 初始化日志
    tracing_subscriber::fmt()
        .with_target(false)
        .with_level(true)
        .init();

    tracing::info!("WorkBuddy Core Engine 启动中...");

    // 数据库路径
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let db_path = PathBuf::from(home)
        .join(".workbuddy")
        .join("workbuddy.db");

    // 初始化存储
    tracing::info!("初始化数据库: {}", db_path.display());
    let storage = StorageManager::open(&db_path)?;

    // 创建应用状态
    let state = Arc::new(AppState {
        storage: storage.clone(),
    });

    // 启动采集引擎
    tracing::info!("启动采集引擎...");
    let capture_config = CaptureConfig::default();
    let (tx, rx) = mpsc::channel(100);
    let capture_engine = CaptureEngine::new(storage.clone(), capture_config);

    // 在后台运行采集引擎
    tokio::spawn(async move {
        if let Err(e) = capture_engine.run(rx).await {
            tracing::error!("采集引擎错误: {}", e);
        }
    });

    // 启动事件监听器
    tracing::info!("启动事件监听器...");
    let listener_config = ListenerConfig::default();
    let enabled = listener_config.enabled.clone();

    tokio::spawn(async move {
        start_listener(listener_config, tx).await;
    });

    // 启动资源监控器
    tracing::info!("启动资源监控器...");
    tokio::spawn(async move {
        ResourceMonitor::new(enabled).start().await;
    });

    // 启动定时任务调度器
    tracing::info!("启动定时任务调度器...");
    let scheduler = std::sync::Arc::new(Scheduler::new(storage.clone()));
    tokio::spawn(async move {
        scheduler.run().await;
    });

    // 启动 API 服务器
    let addr = "127.0.0.1:7070";
    tracing::info!("启动 REST API 服务器: http://{}", addr);
    start_server(state, addr).await?;

    Ok(())
}
