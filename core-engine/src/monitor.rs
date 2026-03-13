//! 系统资源监控模块
//!
//! 监控 CPU 和内存使用情况，超过阈值时自动暂停采集。

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use sysinfo::System;
use tokio::time::interval;
use tracing::{info, warn};

/// 资源监控器
pub struct ResourceMonitor {
    /// 采集开关（共享引用）
    enabled: Arc<AtomicBool>,
    /// CPU 使用率阈值（%）
    cpu_threshold: f32,
    /// 内存使用阈值（MB）
    memory_threshold: u64,
}

impl ResourceMonitor {
    /// 创建资源监控器
    pub fn new(enabled: Arc<AtomicBool>) -> Self {
        Self {
            enabled,
            cpu_threshold: 80.0,
            memory_threshold: 500, // 500MB
        }
    }

    /// 启动监控循环（每 10 秒检查一次）
    pub async fn start(self) {
        let mut sys = System::new_all();
        let mut ticker = interval(Duration::from_secs(10));

        info!("资源监控器已启动");

        loop {
            ticker.tick().await;
            sys.refresh_all();

            // 获取当前进程
            if let Ok(pid) = sysinfo::get_current_pid() {
                if let Some(process) = sys.process(pid) {
                    let cpu = process.cpu_usage();
                    let memory_mb = process.memory() / 1024 / 1024;

                    // CPU 过高：暂停采集 30 秒
                    if cpu > self.cpu_threshold {
                        warn!(
                            "CPU 使用率过高 ({:.1}%)，暂停采集 30 秒",
                            cpu
                        );
                        self.enabled.store(false, Ordering::Relaxed);
                        tokio::time::sleep(Duration::from_secs(30)).await;
                        self.enabled.store(true, Ordering::Relaxed);
                        info!("恢复采集");
                    }

                    // 内存过高：警告（TODO: 触发清理）
                    if memory_mb > self.memory_threshold {
                        warn!(
                            "内存使用过高 ({} MB)，建议清理旧数据",
                            memory_mb
                        );
                    }

                    info!(
                        "资源使用: CPU {:.1}%, 内存 {} MB",
                        cpu, memory_mb
                    );
                }
            }
        }
    }
}
