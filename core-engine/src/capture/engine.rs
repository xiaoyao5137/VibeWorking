//! CaptureEngine — 核心采集引擎
//!
//! 协调截图、AX 信息抓取、隐私过滤和 SQLite 存储。
//!
//! 设计模式：
//! - 事件通过 `tokio::sync::mpsc::Receiver<CaptureEvent>` 注入
//! - 引擎本身不包含事件监听逻辑（由 `listener` 模块或外部注入）
//! - 这使得引擎在测试中可以完全脱离系统 API 运行

use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tokio::sync::mpsc;
use tracing::{debug, info, warn};

use crate::ipc::IpcClient;
use crate::storage::{
    models::{EventType, NewCapture, NewVectorIndex},
    StorageManager,
};

use super::{
    ax::{get_frontmost_info_async, AXInfo},
    filter::PrivacyFilter,
    screenshot::capture_and_save,
    CaptureError,
};

// ─────────────────────────────────────────────────────────────────────────────
// CaptureConfig
// ─────────────────────────────────────────────────────────────────────────────

/// 采集引擎配置参数
#[derive(Debug, Clone)]
pub struct CaptureConfig {
    /// 截图根目录（绝对路径）
    pub captures_dir: PathBuf,
    /// JPEG 压缩质量 0–100（推荐 80）
    pub screenshot_quality: u8,
    /// 是否启用截图（可在低电量模式下关闭）
    pub enable_screenshot: bool,
    /// 是否启用 Accessibility 信息抓取
    pub enable_ax: bool,
}

impl Default for CaptureConfig {
    fn default() -> Self {
        let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
        Self {
            captures_dir:       PathBuf::from(home).join(".memory-bread").join("captures"),
            screenshot_quality: 80,
            enable_screenshot:  true,
            enable_ax:          true,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CaptureEvent
// ─────────────────────────────────────────────────────────────────────────────

/// 触发一次采集的事件类型
#[derive(Debug, Clone)]
pub enum CaptureEvent {
    /// 前台应用发生切换（最高优先级）
    AppSwitch {
        app_name:  String,
        bundle_id: Option<String>,
        win_title: String,
    },
    /// 鼠标点击（在新位置落点）
    MouseClick { x: f64, y: f64 },
    /// 键盘停顿（2 秒无按键）
    KeyPause {
        /// 停顿前的键盘输入片段（已去除密码框内容）
        input_buffer: String,
    },
    /// 页面/内容滚动
    Scroll,
    /// 定时兜底采集（每 N 分钟触发）
    Periodic,
    /// 用户手动唤醒
    Manual,
}

impl CaptureEvent {
    /// 映射到数据库 event_type 字段。
    pub fn to_event_type(&self) -> EventType {
        match self {
            CaptureEvent::AppSwitch { .. }  => EventType::AppSwitch,
            CaptureEvent::MouseClick { .. } => EventType::MouseClick,
            CaptureEvent::KeyPause { .. }   => EventType::KeyPause,
            CaptureEvent::Scroll            => EventType::Scroll,
            CaptureEvent::Periodic          => EventType::Auto,
            CaptureEvent::Manual            => EventType::Manual,
        }
    }

    /// 提取键盘输入文本（仅 KeyPause 有值）。
    pub fn input_text(&self) -> Option<&str> {
        match self {
            CaptureEvent::KeyPause { input_buffer } => Some(input_buffer),
            _ => None,
        }
    }

    /// 提取事件携带的应用名（AppSwitch 专用）。
    pub fn app_name(&self) -> Option<&str> {
        match self {
            CaptureEvent::AppSwitch { app_name, .. } => Some(app_name),
            _ => None,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CaptureEngine
// ─────────────────────────────────────────────────────────────────────────────

/// 核心采集引擎，协调所有采集步骤。
pub struct CaptureEngine {
    storage: StorageManager,
    config:  CaptureConfig,
    filter:  PrivacyFilter,
    ipc_client: Option<IpcClient>,
}

impl CaptureEngine {
    /// 使用默认隐私过滤器创建引擎。
    pub fn new(storage: StorageManager, config: CaptureConfig) -> Self {
        // 尝试创建 IPC 客户端
        let ipc_client = IpcClient::new();
        let ipc_client = if ipc_client.is_available() {
            info!("AI Sidecar 可用，OCR 功能已启用");
            Some(ipc_client)
        } else {
            warn!("AI Sidecar 不可用，OCR 功能已禁用");
            None
        };

        Self {
            storage,
            config,
            filter: PrivacyFilter::new(),
            ipc_client,
        }
    }

    /// 使用自定义隐私过滤器创建引擎（从数据库 app_filters 加载后使用）。
    pub fn with_filter(
        storage: StorageManager,
        config:  CaptureConfig,
        filter:  PrivacyFilter,
    ) -> Self {
        // 尝试创建 IPC 客户端
        let ipc_client = IpcClient::new();
        let ipc_client = if ipc_client.is_available() {
            info!("AI Sidecar 可用，OCR 功能已启用");
            Some(ipc_client)
        } else {
            warn!("AI Sidecar 不可用，OCR 功能已禁用");
            None
        };

        Self { storage, config, filter, ipc_client }
    }

    // ── 主处理流程 ─────────────────────────────────────────────────────────

    /// 处理一个采集事件：截图 + AX 抓取 + 隐私过滤 + DB 写入。
    ///
    /// 返回 `Ok(Some(id))`：已写入数据库的 capture id（含被过滤的记录）。
    pub async fn process_event(
        &self,
        event: CaptureEvent,
    ) -> Result<Option<i64>, CaptureError> {
        let ts = current_ts_ms();

        // 1. 抓取 Accessibility 信息（异步 + 超时保护）
        let ax_info = if self.config.enable_ax {
            get_frontmost_info_async().await
        } else {
            None
        };

        // 2. 合并事件携带的信息与 AX 抓取结果
        let merged = self.merge_ax_and_event(&event, ax_info);

        // 3. 隐私过滤
        let is_sensitive = self.filter.is_sensitive(
            merged.app_name.as_deref(),
            merged.app_bundle_id.as_deref(),
            merged.focused_role.as_deref(),
            merged.win_title.as_deref(),
        );

        if is_sensitive {
            debug!(
                app = ?merged.app_name,
                "隐私窗口已过滤，记录占位行"
            );
            let id = self.save_capture(
                ts,
                &merged,
                &event,
                None,   // 不截图
                true,   // is_sensitive
            )?;
            return Ok(Some(id));
        }

        // 4. 截图（非敏感才截）
        let screenshot_path = if self.config.enable_screenshot {
            match capture_and_save(&self.config.captures_dir, self.config.screenshot_quality)? {
                Some(result) => {
                    debug!(path = %result.relative_path, "截图已保存");
                    Some(result.relative_path)
                }
                None => None,
            }
        } else {
            None
        };

        // 5. 写入数据库
        let id = self.save_capture(ts, &merged, &event, screenshot_path.clone(), false)?;
        debug!(id, app = ?merged.app_name, event = ?event.to_event_type(), "采集完成");

        // 6. 异步调用 OCR（如果 AX 文本为空且有截图）
        if merged.extracted_text.is_none() && screenshot_path.is_some() {
            if let Some(ref ipc_client) = self.ipc_client {
                let screenshot_path = screenshot_path.unwrap();
                let full_path = self.config.captures_dir.join(&screenshot_path);

                // 先检查 Sidecar 是否在线
                if !ipc_client.ping().await {
                    debug!("AI Sidecar 离线，跳过 OCR");
                } else {
                    // 异步调用 OCR（带超时保护）
                    let ipc_client = ipc_client.clone();
                    let storage = self.storage.clone();
                    tokio::spawn(async move {
                        match tokio::time::timeout(
                            Duration::from_secs(15),
                            tokio::task::spawn_blocking({
                                let client = ipc_client.clone();
                                let path = full_path.to_str().unwrap().to_string();
                                move || client.call_ocr(id, &path)
                            }),
                        )
                        .await
                        {
                            Ok(Ok(Ok(ocr_result))) => {
                                debug!(id, confidence = ocr_result.confidence, "OCR 识别成功");
                                if let Err(e) = storage.update_ocr_text(
                                    id,
                                    &ocr_result.text,
                                    ocr_result.confidence as f32,
                                ) {
                                    warn!(id, "更新 OCR 文本失败: {}", e);
                                    return;
                                }

                                // OCR 成功后，立即触发向量化
                                Self::trigger_embedding(ipc_client, storage, id, ocr_result.text)
                                    .await;
                            }
                            Ok(Ok(Err(e))) => {
                                warn!(id, "OCR 调用失败: {}", e);
                            }
                            Ok(Err(e)) => {
                                warn!(id, "OCR 任务崩溃: {:?}", e);
                            }
                            Err(_) => {
                                warn!(id, "OCR 超时（15 秒）");
                            }
                        }
                    });
                }
            }
        } else if merged.extracted_text.is_some() {
            // 7. 如果 AX 已经有文本，直接触发向量化
            if let Some(ref ipc_client) = self.ipc_client {
                let ipc_client = ipc_client.clone();
                let storage = self.storage.clone();
                let text = merged.extracted_text.unwrap();
                tokio::spawn(async move {
                    Self::trigger_embedding(ipc_client, storage, id, text).await;
                });
            }
        }

        Ok(Some(id))
    }

    /// 启动事件处理循环（生产环境入口）。
    ///
    /// 从 channel 持续接收事件直到发送端关闭。
    pub async fn run(
        self,
        mut rx: mpsc::Receiver<CaptureEvent>,
    ) -> Result<(), CaptureError> {
        info!("CaptureEngine 已启动");

        while let Some(event) = rx.recv().await {
            match self.process_event(event).await {
                Ok(Some(id)) => debug!(id, "事件处理完成"),
                Ok(None)     => {}
                Err(e)       => warn!("事件处理失败: {}", e),
            }
        }

        info!("CaptureEngine 退出（channel 已关闭）");
        Ok(())
    }

    // ── 辅助方法 ──────────────────────────────────────────────────────────

    /// 合并事件内置信息与 AX 抓取结果。
    ///
    /// AppSwitch 事件明确携带 app/bundle/win 信息，直接覆盖 AX 结果。
    /// 其他事件以 AX 结果为准。
    fn merge_ax_and_event(&self, event: &CaptureEvent, ax: Option<AXInfo>) -> AXInfo {
        let mut info = ax.unwrap_or_default();

        if let CaptureEvent::AppSwitch { app_name, bundle_id, win_title } = event {
            info.app_name  = Some(app_name.clone());
            info.win_title = Some(win_title.clone());
            if let Some(bid) = bundle_id {
                info.app_bundle_id = Some(bid.clone());
            }
        }

        info
    }

    /// 构造并写入 captures 记录。
    fn save_capture(
        &self,
        ts:              i64,
        ax:              &AXInfo,
        event:           &CaptureEvent,
        screenshot_path: Option<String>,
        is_sensitive:    bool,
    ) -> Result<i64, CaptureError> {
        let new_capture = NewCapture {
            ts,
            app_name:        ax.app_name.clone(),
            app_bundle_id:   ax.app_bundle_id.clone(),
            // 敏感记录不保存窗口标题
            win_title:       if is_sensitive { None } else { ax.win_title.clone() },
            event_type:      event.to_event_type(),
            // 敏感记录不保存文本
            ax_text:         if is_sensitive { None } else { ax.extracted_text.clone() },
            ax_focused_role: if is_sensitive { None } else { ax.focused_role.clone() },
            ax_focused_id:   if is_sensitive { None } else { ax.focused_id.clone() },
            screenshot_path,
            input_text:      if is_sensitive { None } else { event.input_text().map(str::to_string) },
            is_sensitive,
        };
        Ok(self.storage.insert_capture(&new_capture)?)
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────────────────────────────────────

fn current_ts_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time went backwards")
        .as_millis() as i64
}

impl CaptureEngine {
    /// 触发文本向量化并写入向量库
    ///
    /// 流程：
    /// 1. 调用 AI Sidecar 的 Embedding API
    /// 2. 将向量元数据写入 SQLite vector_index 表
    /// 3. 实际向量数据由 Sidecar 写入 Qdrant
    async fn trigger_embedding(
        ipc_client: IpcClient,
        storage: StorageManager,
        capture_id: i64,
        text: String,
    ) {
        // 文本太短不值得向量化
        if text.trim().len() < 10 {
            debug!(capture_id, "文本过短，跳过向量化");
            return;
        }

        // 调用 Embedding API
        match ipc_client.call_embed(capture_id, vec![text.clone()]) {
            Ok(embed_result) => {
                debug!(
                    capture_id,
                    vector_count = embed_result.vectors.len(),
                    "Embedding 成功"
                );

                // 为每个向量生成唯一的 point_id（Qdrant 使用 UUID）
                let point_id = uuid::Uuid::new_v4().to_string();

                // 写入 vector_index 元数据
                let index = NewVectorIndex {
                    capture_id,
                    qdrant_point_id: point_id,
                    chunk_index: 0, // 单文本不分块
                    chunk_text: text,
                    model_name: "bge-m3".to_string(), // 与 AI Sidecar 保持一致
                    created_at: current_ts_ms(),
                };

                if let Err(e) = storage.insert_vector_index(&index) {
                    warn!(capture_id, "写入向量索引元数据失败: {}", e);
                } else {
                    debug!(capture_id, "向量索引元数据已写入");
                }
            }
            Err(e) => {
                warn!(capture_id, "Embedding 调用失败: {}", e);
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 测试
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::repo::capture::CaptureFilter;

    /// 创建测试用引擎（关闭截图和 AX，全部走 mock）
    fn make_engine() -> CaptureEngine {
        let storage = StorageManager::open_in_memory().unwrap();
        let config = CaptureConfig {
            enable_screenshot: false,
            enable_ax:         false,
            ..Default::default()
        };
        CaptureEngine::new(storage, config)
    }

    // ── 单事件处理 ────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_mouse_click_stored() {
        let engine = make_engine();
        let id = engine
            .process_event(CaptureEvent::MouseClick { x: 100.0, y: 200.0 })
            .await
            .unwrap()
            .unwrap();

        let rec = engine.storage.get_capture(id).unwrap().unwrap();
        assert_eq!(rec.event_type, "mouse_click");
        assert!(!rec.is_sensitive);
        assert!(rec.screenshot_path.is_none()); // 截图已禁用
    }

    #[tokio::test]
    async fn test_key_pause_stores_input_text() {
        let engine = make_engine();
        let id = engine
            .process_event(CaptureEvent::KeyPause {
                input_buffer: "你好世界".into(),
            })
            .await
            .unwrap()
            .unwrap();

        let rec = engine.storage.get_capture(id).unwrap().unwrap();
        assert_eq!(rec.event_type, "key_pause");
        assert_eq!(rec.input_text.as_deref(), Some("你好世界"));
    }

    #[tokio::test]
    async fn test_app_switch_stores_app_info() {
        let engine = make_engine();
        let id = engine
            .process_event(CaptureEvent::AppSwitch {
                app_name:  "Feishu".into(),
                bundle_id: Some("com.feishu.feishu".into()),
                win_title: "工作群".into(),
            })
            .await
            .unwrap()
            .unwrap();

        let rec = engine.storage.get_capture(id).unwrap().unwrap();
        assert_eq!(rec.event_type, "app_switch");
        assert_eq!(rec.app_name.as_deref(), Some("Feishu"));
        assert_eq!(rec.app_bundle_id.as_deref(), Some("com.feishu.feishu"));
        assert_eq!(rec.win_title.as_deref(), Some("工作群"));
    }

    #[tokio::test]
    async fn test_periodic_event() {
        let engine = make_engine();
        let id = engine
            .process_event(CaptureEvent::Periodic)
            .await
            .unwrap()
            .unwrap();

        let rec = engine.storage.get_capture(id).unwrap().unwrap();
        assert_eq!(rec.event_type, "auto");
    }

    #[tokio::test]
    async fn test_manual_event() {
        let engine = make_engine();
        let id = engine
            .process_event(CaptureEvent::Manual)
            .await
            .unwrap()
            .unwrap();

        let rec = engine.storage.get_capture(id).unwrap().unwrap();
        assert_eq!(rec.event_type, "manual");
    }

    // ── 隐私过滤 ──────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_blocked_app_records_sensitive_row() {
        let storage = StorageManager::open_in_memory().unwrap();
        let config = CaptureConfig {
            enable_screenshot: false,
            enable_ax:         false,
            ..Default::default()
        };
        let filter = PrivacyFilter::new()
            .with_extra_blocked_apps(&["SecretApp".into()]);
        let engine = CaptureEngine::with_filter(storage, config, filter);

        let id = engine
            .process_event(CaptureEvent::AppSwitch {
                app_name:  "SecretApp".into(),
                bundle_id: None,
                win_title: "Secret Window".into(),
            })
            .await
            .unwrap()
            .unwrap();

        let rec = engine.storage.get_capture(id).unwrap().unwrap();
        assert!(rec.is_sensitive,         "应标记为敏感");
        assert!(rec.ax_text.is_none(),    "敏感记录不含文本");
        assert!(rec.win_title.is_none(),  "敏感记录不含标题");
        assert!(rec.input_text.is_none(), "敏感记录不含输入");
        // app_name 保留（用于统计）
        assert_eq!(rec.app_name.as_deref(), Some("SecretApp"));
    }

    #[tokio::test]
    async fn test_default_blocked_app_1password() {
        let storage = StorageManager::open_in_memory().unwrap();
        let config = CaptureConfig {
            enable_screenshot: false,
            enable_ax:         false,
            ..Default::default()
        };
        let engine = CaptureEngine::new(storage, config);

        let id = engine
            .process_event(CaptureEvent::AppSwitch {
                app_name:  "1Password".into(),
                bundle_id: None,
                win_title: "Unlock 1Password".into(),
            })
            .await
            .unwrap()
            .unwrap();

        let rec = engine.storage.get_capture(id).unwrap().unwrap();
        assert!(rec.is_sensitive);
    }

    // ── channel 事件循环 ──────────────────────────────────────────────────

    #[tokio::test]
    async fn test_run_loop_processes_multiple_events() {
        let storage = StorageManager::open_in_memory().unwrap();
        let storage_clone = storage.clone();

        let config = CaptureConfig {
            enable_screenshot: false,
            enable_ax:         false,
            ..Default::default()
        };
        let engine = CaptureEngine::new(storage, config);
        let (tx, rx) = mpsc::channel::<CaptureEvent>(16);

        // 发送 3 个事件后关闭 channel
        tx.send(CaptureEvent::Manual).await.unwrap();
        tx.send(CaptureEvent::Periodic).await.unwrap();
        tx.send(CaptureEvent::Scroll).await.unwrap();
        drop(tx); // channel 关闭后 run() 返回

        engine.run(rx).await.unwrap();

        let list = storage_clone.list_captures(&CaptureFilter::new()).unwrap();
        assert_eq!(list.len(), 3, "应有 3 条采集记录");
    }

    // ── CaptureEvent 方法 ─────────────────────────────────────────────────

    #[test]
    fn test_event_to_event_type_mapping() {
        use crate::storage::models::EventType;
        assert_eq!(CaptureEvent::Periodic.to_event_type(),                 EventType::Auto);
        assert_eq!(CaptureEvent::Manual.to_event_type(),                   EventType::Manual);
        assert_eq!(CaptureEvent::Scroll.to_event_type(),                   EventType::Scroll);
        assert_eq!(CaptureEvent::MouseClick { x: 0.0, y: 0.0 }.to_event_type(), EventType::MouseClick);
        assert_eq!(
            CaptureEvent::KeyPause { input_buffer: "".into() }.to_event_type(),
            EventType::KeyPause
        );
        assert_eq!(
            CaptureEvent::AppSwitch {
                app_name: "".into(), bundle_id: None, win_title: "".into()
            }.to_event_type(),
            EventType::AppSwitch
        );
    }

    #[test]
    fn test_event_input_text() {
        let e1 = CaptureEvent::KeyPause { input_buffer: "hello".into() };
        assert_eq!(e1.input_text(), Some("hello"));

        let e2 = CaptureEvent::Manual;
        assert!(e2.input_text().is_none());

        let e3 = CaptureEvent::MouseClick { x: 1.0, y: 2.0 };
        assert!(e3.input_text().is_none());
    }

    #[test]
    fn test_event_app_name() {
        let e = CaptureEvent::AppSwitch {
            app_name: "Chrome".into(),
            bundle_id: None,
            win_title: "Google".into(),
        };
        assert_eq!(e.app_name(), Some("Chrome"));
        assert!(CaptureEvent::Manual.app_name().is_none());
    }

    // ── merge_ax_and_event ────────────────────────────────────────────────

    #[test]
    fn test_merge_uses_ax_for_non_app_switch() {
        let engine = make_engine();
        let ax_info = AXInfo {
            app_name:  Some("Chrome".into()),
            win_title: Some("Google Search".into()),
            ..Default::default()
        };
        let merged = engine.merge_ax_and_event(&CaptureEvent::Manual, Some(ax_info));
        assert_eq!(merged.app_name.as_deref(), Some("Chrome"));
        assert_eq!(merged.win_title.as_deref(), Some("Google Search"));
    }

    #[test]
    fn test_merge_app_switch_overrides_ax() {
        let engine = make_engine();
        let ax_info = AXInfo {
            app_name:  Some("OldApp".into()),
            win_title: Some("Old Window".into()),
            ..Default::default()
        };
        let event = CaptureEvent::AppSwitch {
            app_name:  "NewApp".into(),
            bundle_id: Some("com.new.app".into()),
            win_title: "New Window".into(),
        };
        let merged = engine.merge_ax_and_event(&event, Some(ax_info));
        assert_eq!(merged.app_name.as_deref(), Some("NewApp"));
        assert_eq!(merged.win_title.as_deref(), Some("New Window"));
        assert_eq!(merged.app_bundle_id.as_deref(), Some("com.new.app"));
    }
}
