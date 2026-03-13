"""
MiniCPM-V 2.6 VLM 后端

使用 transformers 库加载 MiniCPM-V（本地端侧 VLM）。
支持 CPU 推理（性能有限）和 MPS（Apple Silicon 加速）。

也可通过 llama.cpp 加载 gguf 量化版（更轻量）。
"""

from __future__ import annotations

import json
import logging
import os

from .backend import SceneType, VlmBackend, VlmOutput

logger = logging.getLogger(__name__)

_DEFAULT_MODEL    = "openbmb/MiniCPM-V-2_6"
_DEFAULT_PROMPT   = (
    "请分析这张截图，描述用户正在做什么（工作场景），"
    "识别当前场景类型（如：文档编写、IM 聊天、浏览器、代码编写、表格、视频会议、空闲等），"
    "并提取 3-5 个关键词标签。"
    "以 JSON 格式返回：{\"description\":\"...\",\"scene\":\"...\",\"tags\":[...]}"
)

_SCENE_MAP = {
    "文档编写": SceneType.DOC_WRITING,
    "doc_writing":  SceneType.DOC_WRITING,
    "IM聊天":  SceneType.IM_CHAT,
    "im_chat":       SceneType.IM_CHAT,
    "浏览器":   SceneType.BROWSING,
    "browsing":      SceneType.BROWSING,
    "代码编写":  SceneType.CODING,
    "coding":        SceneType.CODING,
    "表格":     SceneType.SPREADSHEET,
    "spreadsheet":   SceneType.SPREADSHEET,
    "视频会议":  SceneType.VIDEO_MEETING,
    "video_meeting": SceneType.VIDEO_MEETING,
    "空闲":     SceneType.IDLE,
    "idle":          SceneType.IDLE,
}


class MiniCpmVBackend(VlmBackend):
    """
    MiniCPM-V 本地 VLM 后端。

    首次调用 analyze() 时懒加载模型。
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        device:     str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._device     = device
        self._model      = None
        self._tokenizer  = None

    def is_available(self) -> bool:
        try:
            import transformers  # type: ignore  # noqa: F401
            import torch         # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze(self, image_path: str, prompt: str = _DEFAULT_PROMPT) -> VlmOutput:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"截图文件不存在: {image_path}")
        if not self.is_available():
            raise RuntimeError("transformers / torch 未安装，MiniCPM-V 不可用")

        self._ensure_loaded()

        from PIL import Image  # type: ignore
        img = Image.open(image_path).convert("RGB")

        msgs = [{"role": "user", "content": [img, prompt]}]
        response = self._model.chat(  # type: ignore[union-attr]
            image   = None,
            msgs    = msgs,
            tokenizer = self._tokenizer,
        )

        return self._parse_response(response)

    @property
    def model_name(self) -> str:
        return self._model_name

    # ── 内部 ──────────────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._model is None:
            from transformers import AutoModel, AutoTokenizer  # type: ignore
            logger.info("正在加载 MiniCPM-V 模型: %s", self._model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_name, trust_remote_code=True
            )
            self._model = AutoModel.from_pretrained(
                self._model_name, trust_remote_code=True
            ).to(self._device).eval()
            logger.info("MiniCPM-V 模型加载完成")

    @staticmethod
    def _parse_response(text: str) -> VlmOutput:
        """解析模型输出的 JSON 字符串，若解析失败则返回原始文本"""
        try:
            # 提取 JSON 部分（模型可能在 JSON 前后加额外文字）
            start = text.find("{")
            end   = text.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(text[start:end])
                scene_str = data.get("scene", "")
                scene = _SCENE_MAP.get(scene_str, SceneType.UNKNOWN)
                return VlmOutput(
                    description = data.get("description", text),
                    scene_type  = scene,
                    tags        = data.get("tags", []),
                )
        except (json.JSONDecodeError, KeyError):
            pass
        return VlmOutput(description=text, scene_type=SceneType.UNKNOWN)
