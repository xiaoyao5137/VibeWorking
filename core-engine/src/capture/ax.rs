//! Accessibility Tree 信息抓取
//!
//! macOS：通过 `osascript` 调用 System Events 获取前台应用名 / 窗口标题。
//! 未来可升级为直接调用 AXUIElement API（需要 Accessibility 权限）。
//!
//! 其他平台：返回 None，由调用方降级到 OCR。

/// 从 Accessibility Tree 抓取到的前台应用信息
#[derive(Debug, Clone, Default)]
pub struct AXInfo {
    /// 前台应用名称，如 "Feishu"
    pub app_name:       Option<String>,
    /// macOS Bundle ID，如 "com.feishu.feishu"
    pub app_bundle_id:  Option<String>,
    /// 窗口标题
    pub win_title:      Option<String>,
    /// 当前焦点元素的 AX Role，如 "AXTextField"（用于密码框检测）
    pub focused_role:   Option<String>,
    /// 当前焦点元素的标识符（用于执行器精确定位）
    pub focused_id:     Option<String>,
    /// 从 AX Tree 提取的文本内容（最优路径，失败则降级 OCR）
    pub extracted_text: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TextExtractor {
    Chrome,
    Safari,
    WeChat,
    VSCode,
    Generic,
}

impl TextExtractor {
    fn as_str(self) -> &'static str {
        match self {
            Self::Chrome => "chrome",
            Self::Safari => "safari",
            Self::WeChat => "wechat",
            Self::VSCode => "vscode",
            Self::Generic => "generic",
        }
    }
}

fn extractor_for_app_name(app_name: &str) -> TextExtractor {
    match app_name {
        "Google Chrome" | "Google Chrome Canary" => TextExtractor::Chrome,
        "Safari" => TextExtractor::Safari,
        "WeChat" | "微信" => TextExtractor::WeChat,
        "Code" | "Visual Studio Code" => TextExtractor::VSCode,
        _ => TextExtractor::Generic,
    }
}

/// 获取当前前台应用的 AX 信息（同步版本，已废弃）。
///
/// 失败（无权限 / AX 不支持 / 超时）时返回 None，由调用方降级到 OCR。
#[deprecated(note = "使用 get_frontmost_info_async 替代")]
pub fn get_frontmost_info() -> Option<AXInfo> {
    #[cfg(all(target_os = "macos", not(test)))]
    {
        macos_impl::get_frontmost_info_macos()
    }
    #[cfg(any(not(target_os = "macos"), test))]
    {
        None
    }
}

/// 异步获取当前前台应用的 AX 信息（带超时保护）。
///
/// 使用 spawn_blocking 避免阻塞 tokio 运行时，基础上下文与文本提取分阶段超时。
pub async fn get_frontmost_info_async() -> Option<AXInfo> {
    #[cfg(all(target_os = "macos", not(test)))]
    {
        use std::time::Duration;
        use tracing::{debug, warn};

        let basic_task = tokio::task::spawn_blocking(macos_impl::get_frontmost_basic_info_macos);
        let mut info = match tokio::time::timeout(Duration::from_millis(4000), basic_task).await {
            Ok(Ok(Some(info))) => {
                debug!(
                    app = ?info.app_name,
                    win_title = ?info.win_title,
                    "AX 基础上下文获取成功"
                );
                info
            }
            Ok(Ok(None)) => {
                warn!("AX 基础上下文获取失败");
                return None;
            }
            Ok(Err(e)) => {
                warn!("AX 基础上下文任务失败: {}", e);
                return None;
            }
            Err(_) => {
                warn!("AX 基础上下文获取超时（4000ms）");
                return None;
            }
        };

        if let Some(app_name) = info.app_name.clone() {
            let extractor = extractor_for_app_name(&app_name);
            debug!(app = %app_name, extractor = extractor.as_str(), "AX 文本提取分支已选择");

            let app_name_for_task = app_name.clone();
            let text_task = tokio::task::spawn_blocking(move || {
                macos_impl::extract_ax_text_for_app(&app_name_for_task)
            });

            match tokio::time::timeout(Duration::from_millis(1200), text_task).await {
                Ok(Ok(Some(text))) => {
                    debug!(
                        app = %app_name,
                        extractor = extractor.as_str(),
                        text_len = text.len(),
                        "AX 文本提取成功"
                    );
                    info.extracted_text = Some(text);
                }
                Ok(Ok(None)) => {
                    debug!(
                        app = %app_name,
                        extractor = extractor.as_str(),
                        "AX 文本提取为空，等待 OCR 兜底"
                    );
                }
                Ok(Err(e)) => {
                    warn!(
                        app = %app_name,
                        extractor = extractor.as_str(),
                        "AX 文本提取任务失败: {}",
                        e
                    );
                }
                Err(_) => {
                    warn!(
                        app = %app_name,
                        extractor = extractor.as_str(),
                        "AX 文本提取超时（1200ms）"
                    );
                }
            }
        }

        Some(info)
    }
    #[cfg(any(not(target_os = "macos"), test))]
    {
        None
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// macOS 实现
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(all(target_os = "macos", not(test)))]
mod macos_impl {
    use super::{extractor_for_app_name, AXInfo, TextExtractor};
    use std::process::Command;
    use tracing::{debug, warn};

    fn run_osascript(script: &str, stage: &str) -> Result<String, String> {
        let output = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .map_err(|e| format!("启动 osascript 失败: {e}"))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            let status = output.status.code().map_or_else(|| "signal".to_string(), |c| c.to_string());
            return Err(format!("stage={stage} exit={status} stderr={stderr}"));
        }

        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    }

    pub fn get_frontmost_info_macos() -> Option<AXInfo> {
        let mut info = get_frontmost_basic_info_macos()?;
        let app_name = info.app_name.clone()?;
        info.extracted_text = extract_ax_text_for_app(&app_name);
        Some(info)
    }

    pub fn get_frontmost_basic_info_macos() -> Option<AXInfo> {
        let basic_script = r#"
            tell application "System Events"
                set front_process to first application process whose frontmost is true
                set app_name to name of front_process
                set win_title to ""
                try
                    set win_title to name of front window of front_process
                end try
                return app_name & "|" & win_title
            end tell
        "#;

        let raw = match run_osascript(basic_script, "basic_context") {
            Ok(raw) => raw,
            Err(err) => {
                warn!("AX 基础脚本失败: {}", err);
                return None;
            }
        };

        let parts: Vec<&str> = raw.splitn(2, '|').collect();
        let app_name = parts.first().map(|s| s.trim().to_string()).filter(|s| !s.is_empty());
        let win_title = parts.get(1).map(|s| s.trim().to_string()).filter(|s| !s.is_empty());

        if app_name.is_none() {
            warn!(raw = %raw, "AX 基础脚本未返回有效 app_name");
            return None;
        }

        Some(AXInfo {
            app_name,
            win_title,
            ..Default::default()
        })
    }

    /// 按已知前台应用名提取 AX 文本内容。
    ///
    /// 针对常见应用（Chrome、Safari、VSCode 等）使用特定的提取方法。
    pub fn extract_ax_text_for_app(app_name: &str) -> Option<String> {
        let extractor = extractor_for_app_name(app_name);
        debug!(app = %app_name, extractor = extractor.as_str(), "开始 AX 文本提取");

        match extractor {
            TextExtractor::Chrome => extract_chrome_text(),
            TextExtractor::Safari => extract_safari_text(),
            TextExtractor::WeChat => extract_wechat_text(),
            TextExtractor::VSCode => extract_vscode_text(),
            TextExtractor::Generic => extract_generic_text(),
        }
    }

    /// 提取 Chrome 浏览器的页面文本
    fn extract_chrome_text() -> Option<String> {
        let script = r#"
            tell application "Google Chrome"
                if (count of windows) > 0 then
                    set front_win to front window
                    if (count of tabs of front_win) > 0 then
                        set active_tab to active tab of front_win
                        try
                            -- 执行 JavaScript 获取页面文本
                            set page_text to execute active_tab javascript "
                                (function() {
                                    var title = document.title;
                                    var body = document.body;
                                    if (!body) return title;

                                    var clone = body.cloneNode(true);
                                    var scripts = clone.getElementsByTagName('script');
                                    var styles = clone.getElementsByTagName('style');
                                    for (var i = scripts.length - 1; i >= 0; i--) {
                                        scripts[i].remove();
                                    }
                                    for (var i = styles.length - 1; i >= 0; i--) {
                                        styles[i].remove();
                                    }

                                    var text = clone.innerText || clone.textContent || '';
                                    text = text.replace(/\\s+/g, ' ').trim();
                                    if (text.length > 5000) {
                                        text = text.substring(0, 5000) + '...';
                                    }
                                    return title + '\\n\\n' + text;
                                })()
                            "
                            return page_text
                        end try
                    end if
                end if
            end tell
            return ""
        "#;

        match run_osascript(script, "chrome_text") {
            Ok(text) if !text.is_empty() => Some(text),
            Ok(_) => None,
            Err(err) => {
                debug!("Chrome AX 文本提取失败: {}", err);
                None
            }
        }
    }

    /// 提取 Safari 浏览器的页面文本
    fn extract_safari_text() -> Option<String> {
        let script = r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    set front_win to front window
                    if (count of tabs of front_win) > 0 then
                        set active_tab to current tab of front_win
                        try
                            set page_text to do JavaScript "
                                (function() {
                                    var title = document.title;
                                    var body = document.body;
                                    if (!body) return title;
                                    var text = body.innerText || body.textContent || '';
                                    text = text.replace(/\\s+/g, ' ').trim();
                                    if (text.length > 5000) {
                                        text = text.substring(0, 5000) + '...';
                                    }
                                    return title + '\\n\\n' + text;
                                })()
                            " in active_tab
                            return page_text
                        end try
                    end if
                end if
            end tell
            return ""
        "#;

        match run_osascript(script, "safari_text") {
            Ok(text) if !text.is_empty() => Some(text),
            Ok(_) => None,
            Err(err) => {
                debug!("Safari AX 文本提取失败: {}", err);
                None
            }
        }
    }

    /// 提取 WeChat 的聊天文本（优先遍历静态文本与文本区域）
    fn extract_wechat_text() -> Option<String> {
        let script = r#"
            tell application "System Events"
                set front_process to first application process whose frontmost is true
                if name of front_process is not "WeChat" and name of front_process is not "微信" then
                    return ""
                end if

                set text_content to ""
                try
                    set front_win to front window of front_process

                    try
                        set static_items to entire contents of front_win whose role is in {"AXStaticText", "AXTextArea", "AXTextField"}
                        repeat with ui_elem in static_items
                            try
                                set val to value of ui_elem as string
                                if val is not "" then
                                    set text_content to text_content & val & linefeed
                                end if
                            end try
                        end repeat
                    end try

                    if text_content is "" then
                        try
                            set all_ui to entire contents of front_win
                            repeat with ui_elem in all_ui
                                try
                                    set role_name to role of ui_elem as string
                                    if role_name is "AXStaticText" or role_name is "AXTextArea" or role_name is "AXTextField" then
                                        if value of ui_elem is not missing value then
                                            set val to value of ui_elem as string
                                            if val is not "" then
                                                set text_content to text_content & val & linefeed
                                            end if
                                        end if
                                    end if
                                end try
                            end repeat
                        end try
                    end if
                end try

                return text_content
            end tell
        "#;

        match run_osascript(script, "wechat_text") {
            Ok(text) if !text.trim().is_empty() => Some(text.trim().to_string()),
            Ok(_) => {
                debug!("WeChat AX 文本提取为空，回退 generic 提取");
                extract_generic_text()
            }
            Err(err) => {
                debug!("WeChat AX 文本提取失败: {}，回退 generic 提取", err);
                extract_generic_text()
            }
        }
    }

    /// 提取 VSCode 的文本（当前回退到 generic 提取）
    fn extract_vscode_text() -> Option<String> {
        debug!("VSCode 不支持专用 AppleScript，回退 generic 提取");
        extract_generic_text()
    }

    /// 通用文本提取（使用 System Events）
    fn extract_generic_text() -> Option<String> {
        let script = r#"
            tell application "System Events"
                set front_process to first application process whose frontmost is true
                set text_content to ""
                try
                    set front_win to front window of front_process
                    set all_ui to entire contents of front_win
                    repeat with ui_elem in all_ui
                        try
                            if value of ui_elem is not missing value then
                                set val to value of ui_elem as string
                                if val is not "" then
                                    set text_content to text_content & val & " "
                                end if
                            end if
                        end try
                    end repeat
                end try
                return text_content
            end tell
        "#;

        match run_osascript(script, "generic_text") {
            Ok(text) if !text.is_empty() && text.len() > 10 => Some(text),
            Ok(text) => {
                debug!(text_len = text.len(), "generic AX 文本过短或为空");
                None
            }
            Err(err) => {
                debug!("generic AX 文本提取失败: {}", err);
                None
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

    #[test]
    fn test_ax_info_default() {
        let info = AXInfo::default();
        assert!(info.app_name.is_none());
        assert!(info.win_title.is_none());
        assert!(info.extracted_text.is_none());
    }

    #[test]
    fn test_ax_info_partial_construction() {
        let info = AXInfo {
            app_name:    Some("Feishu".into()),
            win_title:   Some("工作群".into()),
            focused_role: Some("AXTextField".into()),
            ..Default::default()
        };
        assert_eq!(info.app_name.as_deref(), Some("Feishu"));
        assert_eq!(info.win_title.as_deref(), Some("工作群"));
        assert_eq!(info.focused_role.as_deref(), Some("AXTextField"));
        assert!(info.extracted_text.is_none());
    }

    #[test]
    fn test_get_frontmost_returns_none_in_test() {
        let result = get_frontmost_info();
        assert!(result.is_none(), "测试环境应返回 None");
    }

    #[test]
    fn test_ax_info_clone() {
        let info = AXInfo {
            app_name: Some("VSCode".into()),
            ..Default::default()
        };
        let cloned = info.clone();
        assert_eq!(info.app_name, cloned.app_name);
    }

    #[test]
    fn test_extractor_for_app_name_routes_correctly() {
        assert_eq!(extractor_for_app_name("Google Chrome"), TextExtractor::Chrome);
        assert_eq!(extractor_for_app_name("Safari"), TextExtractor::Safari);
        assert_eq!(extractor_for_app_name("WeChat"), TextExtractor::WeChat);
        assert_eq!(extractor_for_app_name("微信"), TextExtractor::WeChat);
        assert_eq!(extractor_for_app_name("Code"), TextExtractor::VSCode);
        assert_eq!(extractor_for_app_name("Visual Studio Code"), TextExtractor::VSCode);
        assert_eq!(extractor_for_app_name("WeCom"), TextExtractor::Generic);
    }
}
