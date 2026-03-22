"""
Dispatcher 路由与集成测试

测试覆盖：
- ping  → PingResult (sidecar_version, pong=True)
- ocr   → OcrWorker 处理（inject mock engine）
- embed → EmbedWorker 路由
- asr   → AsrWorker 路由
- vlm   → VlmWorker 路由
- 未知任务类型 → NOT_IMPLEMENTED 错误响应
- 响应 ID 与请求 ID 对应
- latency_ms 字段存在且 >= 0
"""

from __future__ import annotations

import pytest

from dispatcher        import Dispatcher
from ocr.backends.base import OcrBox, OcrOutput
from ocr.engine        import OcrEngine
from tests.conftest    import MockOcrBackend
from memory_bread_ipc     import IpcResponse, ResponseStatus


# ─────────────────────────────────────────────────────────────────────────────
# ping 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestDispatcherPing:
    async def test_ping_returns_ok(self, make_ping_request):
        d    = Dispatcher()
        req  = make_ping_request()
        resp = await d.dispatch(req)

        assert resp.status == ResponseStatus.OK
        assert resp.id == req.id

    async def test_ping_result_has_pong(self, make_ping_request):
        d    = Dispatcher()
        req  = make_ping_request()
        resp = await d.dispatch(req)

        assert resp.result is not None
        assert resp.result.pong is True

    async def test_ping_has_sidecar_version(self, make_ping_request):
        d    = Dispatcher()
        req  = make_ping_request()
        resp = await d.dispatch(req)

        assert isinstance(resp.result.sidecar_version, str)
        assert len(resp.result.sidecar_version) > 0

    async def test_ping_latency_non_negative(self, make_ping_request):
        d    = Dispatcher()
        req  = make_ping_request()
        resp = await d.dispatch(req)

        assert resp.latency_ms >= 0


# ─────────────────────────────────────────────────────────────────────────────
# ocr 路由测试（注入 mock engine）
# ─────────────────────────────────────────────────────────────────────────────

class TestDispatcherOcr:
    def _make_dispatcher_with_mock(self, text: str = "dispatcher OCR 结果"):
        """创建使用 MockOcrBackend 的 Dispatcher"""
        d = Dispatcher()
        mock   = MockOcrBackend(output=OcrOutput(
            boxes=[OcrBox(text=text, confidence=0.9)]
        ))
        engine = OcrEngine(primary=mock, fallback=MockOcrBackend(available=False))
        from ocr.worker import OcrWorker
        d._ocr_worker = OcrWorker(engine=engine)   # 直接注入，绕过懒加载
        return d

    async def test_ocr_routes_to_worker(self, jpeg_image_path, make_ocr_request):
        d    = self._make_dispatcher_with_mock()
        req  = make_ocr_request(screenshot_path=jpeg_image_path)
        resp = await d.dispatch(req)

        assert resp.status == ResponseStatus.OK
        assert resp.result.text == "dispatcher OCR 结果"

    async def test_ocr_response_id_matches(self, jpeg_image_path, make_ocr_request):
        d    = self._make_dispatcher_with_mock()
        req  = make_ocr_request(screenshot_path=jpeg_image_path)
        resp = await d.dispatch(req)

        assert resp.id == req.id

    async def test_ocr_file_not_found_returns_error(
        self, nonexistent_path, make_ocr_request
    ):
        d    = self._make_dispatcher_with_mock()
        req  = make_ocr_request(screenshot_path=nonexistent_path)
        resp = await d.dispatch(req)

        assert resp.status == ResponseStatus.ERROR
        assert "FILE_NOT_FOUND" in (resp.error or "")

    async def test_ocr_worker_lazy_init(self):
        """第一次 OCR 请求触发 Worker 懒加载（不应在 Dispatcher 初始化时报错）"""
        d = Dispatcher()
        assert d._ocr_worker is None  # 初始化时不创建 Worker


# ─────────────────────────────────────────────────────────────────────────────
# 未实现任务类型
# ─────────────────────────────────────────────────────────────────────────────

class TestDispatcherUnknown:
    async def test_unknown_type_returns_not_implemented(self, make_ping_request):
        """未知任务类型应返回 NOT_IMPLEMENTED"""
        import time, uuid
        from memory_bread_ipc import IpcRequest, PiiScrubRequest

        d   = Dispatcher()
        req = IpcRequest(
            id=str(uuid.uuid4()),
            ts=int(time.time() * 1000),
            task=PiiScrubRequest(capture_id=1, text="测试文本"),
        )
        resp = await d.dispatch(req)

        assert resp.status == ResponseStatus.ERROR
        assert "NOT_IMPLEMENTED" in (resp.error or "")
        assert resp.id == req.id

    async def test_embed_routes_to_worker(self, make_ping_request):
        """embed 任务应路由到 EmbedWorker（注入 Mock 后端）"""
        import time, uuid
        from memory_bread_ipc import IpcRequest, EmbedRequest
        from embedding.worker import EmbedWorker
        from embedding.model  import EmbeddingModel
        from embedding.base   import EmbeddingBackend, EmbeddingVector

        class _MockBackend(EmbeddingBackend):
            def is_available(self): return True
            def encode(self, texts):
                return [EmbeddingVector(text=t, vector=[0.1, 0.2]) for t in texts]
            @property
            def model_name(self): return "mock"
            @property
            def dimension(self): return 2

        d = Dispatcher()
        d._embed_worker = EmbedWorker(model=EmbeddingModel(backend=_MockBackend()))

        req  = IpcRequest(
            id=str(uuid.uuid4()),
            ts=int(time.time() * 1000),
            task=EmbedRequest(capture_id=1, texts=["hello"]),
        )
        resp = await d.dispatch(req)

        assert resp.status == ResponseStatus.OK
        assert resp.result is not None
        assert resp.id == req.id

    async def test_asr_routes_to_worker(self, make_ping_request):
        """asr 任务应路由到 AsrWorker（注入 Mock 后端）"""
        import time, uuid
        from memory_bread_ipc import IpcRequest
        from memory_bread_ipc.message import AsrRequest
        from asr.worker  import AsrWorker
        from asr.model   import AsrModel
        from asr.backend import AsrBackend, AsrOutput, AsrSegment

        class _MockAsrBackend(AsrBackend):
            def is_available(self): return True
            def transcribe(self, audio_path, language=None):
                return AsrOutput(text="dispatcher asr 测试", language="zh",
                                 segments=[AsrSegment(0.0, 1.0, "dispatcher asr 测试")])
            @property
            def model_name(self): return "mock-asr"

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            # 最小合法 WAV
            header = (
                b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" +
                b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") +
                (1).to_bytes(2, "little") + (16000).to_bytes(4, "little") +
                (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") +
                (16).to_bytes(2, "little") + b"data" + (0).to_bytes(4, "little")
            )
            f.write(header)
            wav_path = f.name

        try:
            d = Dispatcher()
            d._asr_worker = AsrWorker(model=AsrModel(backend=_MockAsrBackend()))

            req = IpcRequest(
                id=str(uuid.uuid4()),
                ts=int(time.time() * 1000),
                task=AsrRequest(capture_id=1, audio_path=wav_path),
            )
            resp = await d.dispatch(req)

            assert resp.status == ResponseStatus.OK
            assert resp.result is not None
            assert resp.id == req.id
        finally:
            os.unlink(wav_path)

    async def test_vlm_routes_to_worker(self, make_ping_request):
        """vlm 任务应路由到 VlmWorker（注入 Mock 后端）"""
        import time, uuid
        from memory_bread_ipc import IpcRequest
        from memory_bread_ipc.message import VlmRequest
        from vlm.worker  import VlmWorker
        from vlm.model   import VlmModel
        from vlm.backend import VlmBackend, VlmOutput, SceneType

        class _MockVlmBackend(VlmBackend):
            def is_available(self): return True
            def analyze(self, image_path, prompt=""):
                return VlmOutput(description="dispatcher vlm 测试",
                                 scene_type=SceneType.CODING, tags=["测试"])
            @property
            def model_name(self): return "mock-vlm"

        import tempfile
        from PIL import Image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            jpg_path = f.name
        img = Image.new("RGB", (4, 4), color=(50, 100, 150))
        img.save(jpg_path, format="JPEG")

        try:
            d = Dispatcher()
            d._vlm_worker = VlmWorker(model=VlmModel(backend=_MockVlmBackend()))

            req = IpcRequest(
                id=str(uuid.uuid4()),
                ts=int(time.time() * 1000),
                task=VlmRequest(capture_id=1, screenshot_path=jpg_path, prompt="测试"),
            )
            resp = await d.dispatch(req)

            assert resp.status == ResponseStatus.OK
            assert resp.result is not None
            assert resp.id == req.id
        finally:
            import os
            os.unlink(jpg_path)


# ─────────────────────────────────────────────────────────────────────────────
# IPC 序列化集成测试（to_frame → JSON 完整性）
# ─────────────────────────────────────────────────────────────────────────────

class TestIpcFrameSerialization:
    async def test_ping_response_serializable(self, make_ping_request):
        """ping 响应能被序列化为合法 IPC 帧"""
        import json

        d    = Dispatcher()
        req  = make_ping_request()
        resp = await d.dispatch(req)

        frame = resp.to_frame()
        assert len(frame) > 4

        msg_len = int.from_bytes(frame[:4], "big")
        payload = json.loads(frame[4:])

        assert payload["id"]     == req.id
        assert payload["status"] == "ok"
        assert payload["result"]["pong"] is True

    async def test_ocr_response_serializable(self, jpeg_image_path, make_ocr_request):
        """OCR 成功响应能被序列化为合法 IPC 帧"""
        import json

        d   = self._make_dispatcher_with_mock()
        req = make_ocr_request(screenshot_path=jpeg_image_path)
        resp = await d.dispatch(req)

        frame   = resp.to_frame()
        payload = json.loads(frame[4:])

        assert payload["status"]            == "ok"
        assert "text"                       in payload["result"]
        assert "confidence"                 in payload["result"]

    def _make_dispatcher_with_mock(self):
        d = Dispatcher()
        mock   = MockOcrBackend(output=OcrOutput(
            boxes=[OcrBox(text="序列化测试", confidence=0.85)]
        ))
        engine = OcrEngine(primary=mock, fallback=MockOcrBackend(available=False))
        from ocr.worker import OcrWorker
        d._ocr_worker = OcrWorker(engine=engine)
        return d
