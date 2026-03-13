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
/// 使用 spawn_blocking 避免阻塞 tokio 运行时，设置 2 秒超时。
pub async fn get_frontmost_info_async() -> Option<AXInfo> {
    #[cfg(all(target_os = "macos", not(test)))]
    {
        use std::time::Duration;
        use tracing::warn;

        // 使用 spawn_blocking 避免阻塞
        let result = tokio::task::spawn_blocking(|| {
            macos_impl::get_frontmost_info_macos()
        });

        // 设置 2 秒超时
        match tokio::time::timeout(Duration::from_secs(2), result).await {
            Ok(Ok(info)) => info,
            Ok(Err(e)) => {
                warn!("AX 信息获取任务失败: {}", e);
                None
            }
            Err(_) => {
                warn!("AX 信息获取超时（2 秒）");
                None
            }
        }
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
    use super::AXInfo;
    use std::process::Command;
    use std::time::Duration;
    use tracing::debug;

    /// 使用 osascript 获取前台应用名 + 窗口标题 + AX 文本。
    ///
    /// 尝试提取窗口的可见文本内容（需要 Accessibility 权限）。
    pub fn get_frontmost_info_macos() -> Option<AXInfo> {
        // 第一步：获取应用名和窗口标题
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

        let output = Command::new("osascript")
            .arg("-e")
            .arg(basic_script)
            .output()
            .ok()?;

        if !output.status.success() {
            debug!("osascript 调用失败");
            return None;
        }

        let raw = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let parts: Vec<&str> = raw.splitn(2, '|').collect();

        let app_name  = parts.first().map(|s| s.trim().to_string()).filter(|s| !s.is_empty());
        let win_title = parts.get(1).map(|s| s.trim().to_string()).filter(|s| !s.is_empty());

        if app_name.is_none() {
            return None;
        }

        // 第二步：尝试提取 AX 文本内容（可能失败，需要权限）
        let extracted_text = extract_ax_text();

        Some(AXInfo {
            app_name,
            win_title,
            extracted_text,
            ..Default::default()
        })
    }

    /// 尝试提取前台窗口的 AX 文本内容。
    ///
    /// 针对常见应用（Chrome、Safari、VSCode 等）使用特定的提取方法。
    fn extract_ax_text() -> Option<String> {
        // 先获取应用名
        let app_name = get_app_name()?;

        match app_name.as_str() {
            "Google Chrome" | "Google Chrome Canary" => extract_chrome_text(),
            "Safari" => extract_safari_text(),
            "Code" | "Visual Studio Code" => extract_vscode_text(),
            _ => extract_generic_text(),
        }
    }

    /// 获取前台应用名
    fn get_app_name() -> Option<String> {
        let script = r#"
            tell application "System Events"
                set front_process to first application process whose frontmost is true
                return name of front_process
            end tell
        "#;

        let output = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .ok()?;

        if output.status.success() {
            let name = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !name.is_empty() {
                return Some(name);
            }
        }
        None
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
                                    // 获取页面标题
                                    var title = document.title;
                                    // 获取页面主要文本内容
                                    var body = document.body;
                                    if (!body) return title;

                                    // 移除 script 和 style 标签
                                    var clone = body.cloneNode(true);
                                    var scripts = clone.getElementsByTagName('script');
                                    var styles = clone.getElementsByTagName('style');
                                    for (var i = scripts.length - 1; i >= 0; i--) {
                                        scripts[i].remove();
                                    }
                                    for (var i = styles.length - 1; i >= 0; i--) {
                                        styles[i].remove();
                                    }

                                    // 获取可见文本
                                    var text = clone.innerText || clone.textContent || '';
                                    // 清理多余空白
                                    text = text.replace(/\\s+/g, ' ').trim();
                                    // 限制长度
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

        let output = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .ok()?;

        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !text.is_empty() {
                return Some(text);
            }
        }
        None
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

        let output = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .ok()?;

        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !text.is_empty() {
                return Some(text);
            }
        }
        None
    }

    /// 提取 VSCode 的文本（当前编辑器内容）
    fn extract_vscode_text() -> Option<String> {
        // VSCode 不支持 AppleScript，返回 None
        // 未来可以通过 VSCode API 或剪贴板实现
        None
    }

    /// 通用文本提取（使用 System Events）
    fn extract_generic_text() -> Option<String> {
        let script = r#"
            tell application "System Events"
                set front_process to first application process whose frontmost is true
                set text_content to ""
                try
                    set front_win to front window of front_process
                    -- 尝试获取所有文本元素
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

        let output = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .ok()?;

        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !text.is_empty() && text.len() > 10 {
                return Some(text);
            }
        }
        None
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
        // 在测试环境中，get_frontmost_info 始终返回 None（不调用系统 API）
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
}
