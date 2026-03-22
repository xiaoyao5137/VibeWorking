//! 系统资源监控模块
//!
//! 监控 CPU 和内存使用情况，超过阈值时自动暂停采集。

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use sysinfo::System;
use tokio::time::interval;
use tracing::{info, warn};

use crate::storage::StorageManager;

/// 资源监控器
pub struct ResourceMonitor {
    /// 采集开关（共享引用）
    enabled: Arc<AtomicBool>,
    /// CPU 使用率阈值（%）
    cpu_threshold: f32,
    /// 内存使用阈值（MB）
    memory_threshold: u64,
    /// 存储管理器
    storage: StorageManager,
}

impl ResourceMonitor {
    /// 创建资源监控器
    pub fn new(enabled: Arc<AtomicBool>, storage: StorageManager) -> Self {
        Self {
            enabled,
            cpu_threshold: 80.0,
            memory_threshold: 500,
            storage,
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

            let now_ms = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as i64;

            let total_mem_mb = sys.total_memory() / 1024 / 1024;
            let used_mem_mb  = sys.used_memory()  / 1024 / 1024;
            let mem_percent  = if total_mem_mb > 0 {
                used_mem_mb as f64 / total_mem_mb as f64 * 100.0
            } else { 0.0 };

            let mut cpu_total: f64 = 0.0;
            let mut cpu_process: f64 = 0.0;
            let mut mem_process_mb: u64 = 0;

            if let Ok(pid) = sysinfo::get_current_pid() {
                if let Some(process) = sys.process(pid) {
                    cpu_process = process.cpu_usage() as f64;
                    mem_process_mb = process.memory() / 1024 / 1024;
                }
            }

            // 全局 CPU（所有核平均）
            cpu_total = sys.cpus().iter().map(|c| c.cpu_usage() as f64).sum::<f64>()
                / sys.cpus().len().max(1) as f64;

            let gpu_name = std::env::var("WORKBUDDY_GPU_NAME").ok();
            let gpu_percent = std::env::var("WORKBUDDY_GPU_PERCENT")
                .ok()
                .and_then(|v| v.parse::<f64>().ok())
                .unwrap_or(0.0);

            // 写入 system_metrics
            let _ = self.storage.with_conn(|conn| {
                conn.execute(
                    "INSERT INTO system_metrics
                     (ts, cpu_total, cpu_process, mem_total_mb, mem_used_mb, mem_process_mb, mem_percent, disk_read_mb, disk_write_mb)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0, 0)",
                    rusqlite::params![
                        now_ms,
                        cpu_total,
                        cpu_process,
                        total_mem_mb as i64,
                        used_mem_mb as i64,
                        mem_process_mb as i64,
                        mem_percent,
                    ],
                )?;
                Ok(())
            });

            // CPU 过高：暂停采集 30 秒
            if cpu_process as f32 > self.cpu_threshold {
                warn!("CPU 使用率过高 ({:.1}%)，暂停采集 30 秒", cpu_process);
                self.enabled.store(false, Ordering::Relaxed);
                tokio::time::sleep(Duration::from_secs(30)).await;
                self.enabled.store(true, Ordering::Relaxed);
                info!("恢复采集");
            }

            if mem_process_mb > self.memory_threshold {
                warn!("内存使用过高 ({} MB)，建议清理旧数据", mem_process_mb);
            }

            info!("资源使用: CPU {:.1}%, 内存 {} MB", cpu_process, mem_process_mb);
        }
    }
}
