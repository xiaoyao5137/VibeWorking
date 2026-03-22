"""
OcrWorker — IPC OCR 任务处理器

接收来自 Rust Core Engine 的 OcrRequest，
调用 OcrEngine 执行识别，将结果封装为 IpcResponse 返回。

设计要点：
- 所有异常在此处被捕获并转换为错误响应，不向上抛出
- 记录处理时间（latency_ms）用于性能监控
- 支持注入自定义 OcrEngine（测试用）
"""

from __future__ import annotations

import asyncio
import logging
import time

from memory_bread_ipc import IpcRequest, IpcResponse, OcrResult

from .engine import OcrEngine

logger = logging.getLogger(__name__)


class OcrWorker:
    """
    处理 IPC OcrRequest 的异步 Worker。

    handle() 在 asyncio 事件循环中运行，但 OcrEngine.process()
    是同步阻塞调用，通过 run_in_executor 在线程池中执行，
    避免阻塞 asyncio 事件循环。
    """

    def __init__(self, engine: OcrEngine | None = None) -> None:
        self._engine = engine or OcrEngine.create_default()

    async def handle(self, req: IpcRequest) -> IpcResponse:
        """
        异步处理一个 OcrRequest。

        将同步的 engine.process() 包装到线程池中执行，
        不阻塞 asyncio 事件循环（兼容高并发场景）。
        """
        t0   = time.monotonic()
        task = req.task  # OcrRequest

        try:
            # 在线程池中执行同步 OCR（避免阻塞事件循环）
            loop   = asyncio.get_running_loop()
            output = await loop.run_in_executor(
                None, self._engine.process, task.screenshot_path
            )

            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "OCR 完成 capture_id=%d | %d行 | 置信度=%.3f | %dms",
                task.capture_id, len(output.boxes), output.confidence, latency_ms,
            )

            result = OcrResult(
                text=output.text,
                confidence=round(output.confidence, 4),
                language=output.language,
            )
            return IpcResponse.make_ok(req.id, result, latency_ms)

        except FileNotFoundError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.warning("OCR 文件不存在 capture_id=%d: %s", task.capture_id, exc)
            return IpcResponse.make_error(
                req.id, "FILE_NOT_FOUND", str(exc), latency_ms
            )

        except RuntimeError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.error("OCR 运行时失败 capture_id=%d: %s", task.capture_id, exc)
            return IpcResponse.make_error(
                req.id, "OCR_FAILED", str(exc), latency_ms
            )

        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.exception("OCR 未预期异常 capture_id=%d", task.capture_id)
            return IpcResponse.make_error(
                req.id, "INTERNAL_ERROR", str(exc), latency_ms
            )
