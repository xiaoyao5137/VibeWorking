//! 截图采集与 JPEG 压缩存储
//!
//! 生产环境：使用 `xcap` crate 采集全屏截图，
//! 转换为 JPEG（质量可配置），存储到时间戳命名的文件。
//!
//! 测试环境：`capture_and_save` 返回 None，不调用系统 API。

use std::path::{Path, PathBuf};

use super::CaptureError;

// ─────────────────────────────────────────────────────────────────────────────
// 公共类型
// ─────────────────────────────────────────────────────────────────────────────

/// 截图保存结果
#[derive(Debug, Clone)]
pub struct ScreenshotResult {
    /// 相对于 captures_dir 的路径（写入数据库 screenshot_path 字段）
    pub relative_path: String,
    /// 截图文件的完整磁盘路径
    pub full_path: PathBuf,
    /// 图像宽度（像素）
    pub width: u32,
    /// 图像高度（像素）
    pub height: u32,
    /// JPEG 文件大小（字节）
    pub file_size: u64,
}

// ─────────────────────────────────────────────────────────────────────────────
// 公共 API
// ─────────────────────────────────────────────────────────────────────────────

/// 采集主显示器截图并以 JPEG 格式存储。
///
/// 返回 `Ok(None)` 表示无可用显示器（无头服务器 / 测试环境）。
pub fn capture_and_save(
    captures_dir: &Path,
    quality:      u8,
) -> Result<Option<ScreenshotResult>, CaptureError> {
    #[cfg(not(test))]
    {
        capture_real(captures_dir, quality)
    }
    #[cfg(test)]
    {
        // 测试环境：不调用系统截图 API，直接返回 None
        let _ = (captures_dir, quality);
        Ok(None)
    }
}

/// 生成截图文件的相对路径。
///
/// 格式：`screenshots/{timestamp_ms}.jpg`
pub fn make_relative_path(ts_ms: i64) -> String {
    format!("screenshots/{}.jpg", ts_ms)
}

// ─────────────────────────────────────────────────────────────────────────────
// 真实截图实现（仅非测试编译）
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(not(test))]
fn capture_real(
    captures_dir: &Path,
    quality:      u8,
) -> Result<Option<ScreenshotResult>, CaptureError> {
    use image::codecs::jpeg::JpegEncoder;
    use image::DynamicImage;
    use std::fs;
    use std::io::BufWriter;
    use std::time::{SystemTime, UNIX_EPOCH};
    use xcap::Monitor;

    let monitors = Monitor::all()
        .map_err(|e| CaptureError::ScreenshotFailed(e.to_string()))?;

    if monitors.is_empty() {
        return Ok(None);
    }

    // 采集主显示器（第一个）
    let rgba_image = monitors[0]
        .capture_image()
        .map_err(|e| CaptureError::ScreenshotFailed(e.to_string()))?;

    let width  = rgba_image.width();
    let height = rgba_image.height();

    let ts_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64;

    let relative_path = make_relative_path(ts_ms);
    let full_path = captures_dir.join(&relative_path);

    // 确保父目录存在
    if let Some(parent) = full_path.parent() {
        fs::create_dir_all(parent)?;
    }

    // RGBA → RGB（JPEG 不支持透明通道）
    let rgb_image = DynamicImage::ImageRgba8(rgba_image).into_rgb8();

    // 编码为 JPEG（指定质量）
    let file   = fs::File::create(&full_path)?;
    let writer = BufWriter::new(file);
    let mut encoder = JpegEncoder::new_with_quality(writer, quality);
    encoder
        .encode_image(&DynamicImage::ImageRgb8(rgb_image))
        .map_err(|e| CaptureError::ImageError(e.to_string()))?;

    let file_size = fs::metadata(&full_path)?.len();

    Ok(Some(ScreenshotResult {
        relative_path,
        full_path,
        width,
        height,
        file_size,
    }))
}

// ─────────────────────────────────────────────────────────────────────────────
// 测试
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_capture_returns_none_in_test_env() {
        let dir = tempdir().unwrap();
        let result = capture_and_save(dir.path(), 80).unwrap();
        assert!(result.is_none(), "测试环境不应产生真实截图");
    }

    #[test]
    fn test_make_relative_path_format() {
        let path = make_relative_path(1_700_000_000_000);
        assert!(path.starts_with("screenshots/"), "应以 screenshots/ 开头");
        assert!(path.ends_with(".jpg"), "应以 .jpg 结尾");
        assert!(path.contains("1700000000000"), "应包含时间戳");
    }

    #[test]
    fn test_make_relative_path_unique() {
        // 不同时间戳应生成不同路径
        let p1 = make_relative_path(1_000_000_000);
        let p2 = make_relative_path(1_000_000_001);
        assert_ne!(p1, p2);
    }

    /// 验证 image crate 的 JPEG 编码流程（不依赖系统截图 API）
    #[test]
    fn test_jpeg_encode_from_raw_pixels() {
        use image::codecs::jpeg::JpegEncoder;
        use image::{DynamicImage, RgbImage};
        use std::io::Cursor;

        // 创建 8×8 纯色 RGB 图像
        let width  = 8u32;
        let height = 8u32;
        let pixels: Vec<u8> = (0..width * height * 3)
            .map(|i| match i % 3 {
                0 => 200, // R
                1 => 100, // G
                _ => 50,  // B
            })
            .collect();

        let rgb_image = RgbImage::from_raw(width, height, pixels).unwrap();
        let dynamic   = DynamicImage::ImageRgb8(rgb_image);

        let mut buf = Cursor::new(Vec::<u8>::new());
        let mut encoder = JpegEncoder::new_with_quality(&mut buf, 80);
        encoder.encode_image(&dynamic).expect("JPEG 编码应成功");

        let bytes = buf.into_inner();
        assert!(!bytes.is_empty(), "JPEG 字节流不应为空");
        // JPEG 文件以 FF D8 开头
        assert_eq!(bytes[0], 0xFF, "JPEG 魔数第1字节");
        assert_eq!(bytes[1], 0xD8, "JPEG 魔数第2字节");
    }

    /// 验证 JPEG 文件可以被 image crate 重新解码
    #[test]
    fn test_jpeg_roundtrip() {
        use image::codecs::jpeg::JpegEncoder;
        use image::{DynamicImage, RgbImage};
        use std::io::Cursor;

        let width  = 4u32;
        let height = 4u32;
        let pixels: Vec<u8> = vec![128u8; (width * height * 3) as usize];

        let rgb   = RgbImage::from_raw(width, height, pixels).unwrap();
        let dyn_  = DynamicImage::ImageRgb8(rgb);

        let mut encoded = Cursor::new(Vec::<u8>::new());
        JpegEncoder::new_with_quality(&mut encoded, 90)
            .encode_image(&dyn_)
            .unwrap();

        // 重新解码
        encoded.set_position(0);
        let decoded = image::load(encoded, image::ImageFormat::Jpeg).unwrap();
        // JPEG 有损，尺寸应保持一致
        assert_eq!(decoded.width(), width);
        assert_eq!(decoded.height(), height);
    }
}
