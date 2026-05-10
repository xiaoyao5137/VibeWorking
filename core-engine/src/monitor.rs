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
            memory_threshold: 500,
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

            // 使用 vm_stat 获取真实内存（包含压缩内存）
            let mem_percent = get_real_memory_usage();

            let mut cpu_process: f64 = 0.0;
            let mut mem_process_mb: u64 = 0;

            if let Ok(pid) = sysinfo::get_current_pid() {
                if let Some(process) = sys.process(pid) {
                    cpu_process = process.cpu_usage() as f64;
                    mem_process_mb = process.memory() / 1024 / 1024;
                }
            }

            // 全局 CPU（所有核平均）
            let cpu_total: f64 = sys.cpus().iter().map(|c| c.cpu_usage() as f64).sum::<f64>()
                / sys.cpus().len().max(1) as f64;

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

            info!(
                "资源使用: CPU {:.1}%, 内存 {} MB, 系统 CPU {:.1}%, 系统内存 {:.1}%",
                cpu_process, mem_process_mb, cpu_total, mem_percent
            );
        }
    }
}

/// 获取真实内存使用率（包含压缩内存）
#[cfg(target_os = "macos")]
fn get_real_memory_usage() -> f64 {
    use std::process::Command;

    let output = match Command::new("vm_stat").output() {
        Ok(o) => o,
        Err(_) => return 0.0,
    };

    let stdout = String::from_utf8_lossy(&output.stdout);

    let mut pages_active = 0u64;
    let mut pages_wired = 0u64;
    let mut pages_compressed = 0u64;
    let mut pages_free = 0u64;
    let mut pages_inactive = 0u64;

    for line in stdout.lines() {
        if line.starts_with("Pages active:") {
            pages_active = parse_vm_value(line);
        } else if line.starts_with("Pages wired down:") {
            pages_wired = parse_vm_value(line);
        } else if line.starts_with("Pages stored in compressor:") {
            pages_compressed = parse_vm_value(line);
        } else if line.starts_with("Pages free:") {
            pages_free = parse_vm_value(line);
        } else if line.starts_with("Pages inactive:") {
            pages_inactive = parse_vm_value(line);
        }
    }

    let total = pages_active + pages_wired + pages_free + pages_inactive;
    if total == 0 {
        return 0.0;
    }

    // macOS 内存模型：compressed 是从 inactive 压缩出来的，不应重复计入
    let used = pages_active + pages_wired;
    (used as f64 / total as f64) * 100.0
}

#[cfg(not(target_os = "macos"))]
fn get_real_memory_usage() -> f64 {
    0.0
}

fn parse_vm_value(line: &str) -> u64 {
    line.split(':')
        .nth(1)
        .and_then(|s| s.trim().trim_end_matches('.').parse().ok())
        .unwrap_or(0)
}
