#!/usr/bin/env python3
"""调试 PaddleOCR 的实际输出格式"""

import tempfile
from PIL import Image, ImageDraw, ImageFont

# 创建测试图片
with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
    test_image_path = f.name
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 30)
    except:
        font = ImageFont.load_default()
    draw.text((20, 30), "测试文字", fill=(0, 0, 0), font=font)
    img.save(test_image_path, format="JPEG", quality=85)

print(f"测试图片: {test_image_path}")

# 加载 PaddleOCR
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang="ch")

# 执行 OCR
print("\n执行 OCR...")
raw = ocr.ocr(test_image_path)

# 打印原始输出
print("\n=== 原始输出类型 ===")
print(f"type(raw): {type(raw)}")
print(f"len(raw): {len(raw) if raw else 'None'}")

if raw:
    print(f"\ntype(raw[0]): {type(raw[0])}")

    # 检查是否是 OCRResult 对象
    result_obj = raw[0]
    print(f"\n=== OCRResult 对象属性 ===")
    print(f"dir(result_obj): {[x for x in dir(result_obj) if not x.startswith('_')]}")

    # 尝试访问常见属性
    if hasattr(result_obj, 'boxes'):
        print(f"\nresult_obj.boxes: {result_obj.boxes}")
    if hasattr(result_obj, 'rec_text'):
        print(f"\nresult_obj.rec_text: {result_obj.rec_text}")
    if hasattr(result_obj, 'rec_score'):
        print(f"\nresult_obj.rec_score: {result_obj.rec_score}")
    if hasattr(result_obj, 'dt_polys'):
        print(f"\nresult_obj.dt_polys: {result_obj.dt_polys}")

    # 打印完整对象
    print(f"\n=== str(result_obj) ===")
    print(str(result_obj))

# 清理
import os
os.unlink(test_image_path)
