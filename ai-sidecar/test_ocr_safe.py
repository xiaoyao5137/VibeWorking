#!/usr/bin/env python3
"""
安全的 OCR 测试脚本 - 监控内存使用

分步测试：
1. 只测试 Mock 后端（无内存压力）
2. 测试 Apple Vision（macOS 原生，内存占用小）
3. 最后测试 PaddleOCR（会加载大模型）

每步都显示内存使用情况。
"""

import gc
import os
import sys
import tempfile
import tracemalloc
from pathlib import Path

# 启动内存追踪
tracemalloc.start()

def get_memory_mb():
    """获取当前内存使用（MB）"""
    current, peak = tracemalloc.get_traced_memory()
    return current / 1024 / 1024, peak / 1024 / 1024

def print_memory(label: str):
    """打印内存使用情况"""
    current, peak = get_memory_mb()
    print(f"[{label}] 当前内存: {current:.1f} MB | 峰值: {peak:.1f} MB")

print("=" * 60)
print("OCR 安全测试 - 内存监控")
print("=" * 60)

# ── 步骤 1: 创建测试图片 ──────────────────────────────────────
print("\n[步骤 1] 创建测试图片...")
from PIL import Image

with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
    test_image_path = f.name
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))
    # 添加一些文字（用于真实 OCR 测试）
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)
    try:
        # 尝试使用系统字体
        font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 20)
    except:
        font = ImageFont.load_default()
    draw.text((10, 15), "测试文字", fill=(0, 0, 0), font=font)
    img.save(test_image_path, format="JPEG", quality=85)

print(f"✓ 测试图片已创建: {test_image_path}")
print_memory("创建图片后")

# ── 步骤 2: 测试 Mock 后端（无内存压力）──────────────────────
print("\n[步骤 2] 测试 Mock 后端（不加载任何模型）...")
from ocr.backends.base import OcrBox, OcrOutput
from ocr.engine import OcrEngine
from tests.conftest import MockOcrBackend

mock_backend = MockOcrBackend(
    output=OcrOutput(boxes=[OcrBox(text="Mock 识别结果", confidence=0.95)])
)
engine_mock = OcrEngine(primary=mock_backend, fallback=None)
result_mock = engine_mock.process(test_image_path)

print(f"✓ Mock OCR 结果: {result_mock.text}")
print_memory("Mock 测试后")

# 清理
del engine_mock, mock_backend, result_mock
gc.collect()

# ── 步骤 3: 跳过 Apple Vision（已知会超时）─────────────────
print("\n[步骤 3] 跳过 Apple Vision 测试")
print("⚠ Apple Vision 使用 swift - 内联脚本，首次编译可能超时/卡死")
print("⚠ 这可能是上次系统死机的原因，暂时跳过")

# ── 步骤 4: 测试 PaddleOCR（会加载大模型，内存密集）────────────
print("\n[步骤 4] 测试 PaddleOCR 后端（会加载模型，约 200-300 MB）...")
print("⚠ 警告: 这将加载 PaddleOCR 模型到内存")
print("如果你的系统内存不足，请按 Ctrl+C 取消")

import time
time.sleep(2)  # 给用户 2 秒时间取消

from ocr.backends.paddle import PaddleBackend

paddle_backend = PaddleBackend(lang="ch")
if paddle_backend.is_available():
    print("正在加载 PaddleOCR 模型（首次加载需要 5-10 秒）...")
    print_memory("加载前")

    engine_paddle = OcrEngine(primary=paddle_backend, fallback=None)
    result_paddle = engine_paddle.process(test_image_path)

    print(f"✓ PaddleOCR 结果: {result_paddle.text}")
    print_memory("PaddleOCR 测试后")

    # 清理
    del engine_paddle, paddle_backend, result_paddle
    gc.collect()
    print_memory("清理后")
else:
    print("⚠ PaddleOCR 不可用")

# ── 清理测试文件 ──────────────────────────────────────────────
os.unlink(test_image_path)
print(f"\n✓ 测试图片已删除: {test_image_path}")

# ── 最终报告 ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("测试完成！")
print_memory("最终状态")
print("=" * 60)

tracemalloc.stop()
