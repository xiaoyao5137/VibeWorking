"""
OCR 后端抽象基类

所有 OCR 后端（PaddleOCR、Apple Vision、Mock）都必须实现此接口。
OcrEngine 通过 backend.is_available() 决定使用哪个后端，通过 backend.run() 执行识别。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# 数据类型
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OcrBox:
    """单个文字检测框"""
    text:       str
    confidence: float                   # 0.0–1.0
    bbox:       list[list[float]] = field(default_factory=list)
    # bbox 格式：[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]（顺时针四点）


@dataclass
class OcrOutput:
    """单张图片的完整 OCR 识别结果"""
    boxes:    list[OcrBox]
    language: str = "zh"                # 主要识别语言（小写 ISO 639-1）

    @property
    def text(self) -> str:
        """将所有文字框按行拼接，过滤空白行"""
        lines = [b.text for b in self.boxes if b.text.strip()]
        return "\n".join(lines)

    @property
    def confidence(self) -> float:
        """所有文字框的平均置信度；无结果时返回 0.0"""
        if not self.boxes:
            return 0.0
        return sum(b.confidence for b in self.boxes) / len(self.boxes)

    @property
    def is_empty(self) -> bool:
        return not any(b.text.strip() for b in self.boxes)


# ─────────────────────────────────────────────────────────────────────────────
# 抽象基类
# ─────────────────────────────────────────────────────────────────────────────

class OcrBackend(ABC):
    """OCR 后端接口"""

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查此后端是否可用（库已安装、平台兼容）。
        引擎在选择后端时先调用此方法，不可用的后端会被跳过。
        """

    @abstractmethod
    def run(self, image_path: str) -> OcrOutput:
        """
        对指定图片文件执行 OCR。

        Args:
            image_path: 图片绝对路径（JPEG/PNG）

        Returns:
            OcrOutput 识别结果

        Raises:
            RuntimeError: 识别过程中发生不可恢复的错误
        """
