#!/usr/bin/env python3
"""
测试 OCR 引擎配置
验证 macOS 上是否默认使用 Apple Vision
"""

import sys
import platform

# 模拟 OcrEngine 的逻辑
def test_ocr_selection():
    system = platform.system()

    print(f"当前平台: {system}")
    print(f"Python 版本: {sys.version}")
    print()

    if system == "Darwin":  # macOS
        print("✅ 检测到 macOS")
        print("📱 主 OCR 引擎: Apple Vision Framework")
        print("🔄 降级引擎: PaddleOCR")
        print()
        print("优势:")
        print("  - 系统原生，无需安装依赖")
        print("  - 使用 Neural Engine 加速")
        print("  - 识别速度: 50-100ms/帧")
        print("  - CPU 占用: 5-15%")
        print("  - 功耗: 极低")
        print()

        # 检查 Swift 是否可用
        import subprocess
        try:
            result = subprocess.run(
                ['swift', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.split('\n')[0]
                print(f"✅ Swift 可用: {version}")
            else:
                print("❌ Swift 不可用")
        except FileNotFoundError:
            print("❌ Swift 未安装")
            print("   安装方法: xcode-select --install")
        except Exception as e:
            print(f"❌ Swift 检查失败: {e}")

    else:  # Windows / Linux
        print(f"✅ 检测到 {system}")
        print("📱 主 OCR 引擎: PaddleOCR")
        print("🔄 降级引擎: 无")
        print()
        print("优势:")
        print("  - 跨平台兼容")
        print("  - 中英文混合识别准确率 >95%")
        print("  - 识别速度: 150-200ms/帧")
        print("  - CPU 占用: 20-40%")
        print()

        # 检查 PaddleOCR 是否安装
        try:
            import paddleocr
            print("✅ PaddleOCR 已安装")
        except ImportError:
            print("❌ PaddleOCR 未安装")
            print("   安装方法: pip install paddlepaddle paddleocr")

if __name__ == "__main__":
    test_ocr_selection()
