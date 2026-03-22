"""
记忆面包 IPC 协议 Python 包

供 AI Sidecar 使用，包含：
- message.py : Pydantic 消息类型（与 Rust 端 serde 类型严格对应）
- transport.py: asyncio Socket 服务端（IpcServer）
"""

from .message import (
    AsrRequest,
    AsrResult,
    AsrSegment,
    EmbedRequest,
    EmbedResult,
    IpcRequest,
    IpcResponse,
    OcrRequest,
    OcrResult,
    PiiScrubRequest,
    PiiScrubResult,
    PingResult,
    ResponseStatus,
    ResultPayload,
    SceneType,
    TaskRequest,
    VlmRequest,
    VlmResult,
)
from .transport import IpcServer, FrameCodec

__all__ = [
    "IpcRequest",
    "IpcResponse",
    "TaskRequest",
    "ResultPayload",
    "ResponseStatus",
    "OcrRequest",
    "OcrResult",
    "AsrRequest",
    "AsrResult",
    "AsrSegment",
    "VlmRequest",
    "VlmResult",
    "SceneType",
    "EmbedRequest",
    "EmbedResult",
    "PiiScrubRequest",
    "PiiScrubResult",
    "PingResult",
    "IpcServer",
    "FrameCodec",
]
