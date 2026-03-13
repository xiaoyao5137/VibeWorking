"""
VLM 后端抽象基类与数据类型

VLM（Visual Language Model）对截图进行语义理解，
识别场景类型（文档编辑、IM 聊天、浏览器等）并提取语义标签。
"""

from __future__ import annotations

from abc         import ABC, abstractmethod
from dataclasses import dataclass, field
from enum        import Enum


class SceneType(str, Enum):
    """工作场景类型"""
    DOC_WRITING   = "doc_writing"
    IM_CHAT       = "im_chat"
    BROWSING      = "browsing"
    CODING        = "coding"
    SPREADSHEET   = "spreadsheet"
    VIDEO_MEETING = "video_meeting"
    IDLE          = "idle"
    UNKNOWN       = "unknown"


@dataclass
class VlmOutput:
    """VLM 分析输出"""
    description: str
    scene_type:  SceneType    = SceneType.UNKNOWN
    tags:        list[str]    = field(default_factory=list)


class VlmBackend(ABC):
    """所有 VLM 后端必须实现的接口"""

    @abstractmethod
    def is_available(self) -> bool:
        """当前环境是否可用"""

    @abstractmethod
    def analyze(self, image_path: str, prompt: str) -> VlmOutput:
        """
        分析截图并返回语义描述。

        Args:
            image_path: 截图路径（JPEG/PNG）
            prompt:     指导模型的提示词

        Returns:
            VlmOutput（含 description / scene_type / tags）
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型标识符"""
