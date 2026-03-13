# AI 模型内存管理问题分析与优化方案

## 问题诊断

### 当前实现的内存问题

通过代码分析，发现 AI Sidecar 存在严重的内存管理问题：

#### 1. **模型常驻内存，永不释放**

**PaddleOCR 后端** (`ai-sidecar/ocr/backends/paddle.py:90-104`):
```python
def _ensure_loaded(self) -> None:
    if self._ocr is not None:
        return
    from paddleocr import PaddleOCR
    self._ocr = PaddleOCR(...)  # 加载后永久驻留
```

**BGE-M3 Embedding 后端** (`ai-sidecar/embedding/bge.py:73-78`):
```python
def _ensure_loaded(self) -> None:
    if self._model is None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(...)  # 加载后永久驻留
```

**问题**:
- PaddleOCR 模型大小：~200MB（检测 + 识别 + 方向分类）
- BGE-M3 模型大小：~2.3GB（1024 维 Transformer）
- **总计：~2.5GB 常驻内存**
- 即使长时间不使用，模型也不会被释放

---

#### 2. **Dispatcher 懒加载但不卸载**

**Dispatcher** (`ai-sidecar/dispatcher.py:83-125`):
```python
def _get_ocr_worker(self):
    if self._ocr_worker is None:
        self._ocr_worker = OcrWorker(engine=OcrEngine.create_default())
    return self._ocr_worker  # 永久持有引用
```

**问题**:
- 所有 Worker 一旦初始化就永久持有模型引用
- 即使用户只用了一次 OCR，模型也会一直占用内存
- 多个模型同时加载时，内存占用可能超过 5GB

---

#### 3. **无空闲检测和自动卸载机制**

当前实现缺少：
- ✗ 模型使用时间追踪
- ✗ 空闲超时自动卸载
- ✗ 内存压力检测
- ✗ 按需加载/卸载策略

---

## 内存占用估算

| 模型 | 大小 | 加载时机 | 卸载时机 |
|------|------|----------|----------|
| PaddleOCR | ~200MB | 首次 OCR | ❌ 永不卸载 |
| BGE-M3 | ~2.3GB | 首次 Embed | ❌ 永不卸载 |
| Whisper (ASR) | ~1.5GB | 首次 ASR | ❌ 永不卸载 |
| MiniCPM-V (VLM) | ~4GB | 首次 VLM | ❌ 永不卸载 |
| **总计** | **~8GB** | - | - |

**实际影响**:
- 用户只用 OCR 功能，也会占用 200MB
- 如果触发过一次 Embedding，内存直接飙升到 2.5GB
- 在 8GB 内存的 Mac 上，WorkBuddy 可能占用 30%+ 内存
- 导致系统频繁 swap，整体卡顿

---

## 优化方案

### 方案 1: 空闲超时自动卸载（推荐）

#### 实现思路
1. 为每个 Worker 添加 `last_used_time` 时间戳
2. 后台线程每 60 秒检查一次
3. 超过 5 分钟未使用的模型自动卸载
4. 下次使用时重新加载（懒加载）

#### 代码实现

**新文件**: `ai-sidecar/model_manager.py`

```python
"""
模型生命周期管理器

职责：
- 追踪模型最后使用时间
- 自动卸载空闲模型
- 提供统一的模型获取接口
"""

import asyncio
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ModelSlot:
    """单个模型的生命周期管理"""

    def __init__(
        self,
        name: str,
        loader: Callable[[], Any],
        idle_timeout: float = 300.0,  # 5 分钟
    ):
        self.name = name
        self._loader = loader
        self._idle_timeout = idle_timeout
        self._model: Optional[Any] = None
        self._last_used: float = 0.0
        self._loading = False

    def get(self) -> Any:
        """获取模型（自动加载）"""
        if self._model is None:
            if self._loading:
                raise RuntimeError(f"模型 {self.name} 正在加载中")
            self._loading = True
            try:
                logger.info("加载模型: %s", self.name)
                self._model = self._loader()
                logger.info("模型加载完成: %s", self.name)
            finally:
                self._loading = False

        self._last_used = time.monotonic()
        return self._model

    def unload(self) -> None:
        """卸载模型"""
        if self._model is not None:
            logger.info("卸载模型: %s", self.name)
            del self._model
            self._model = None
            # 强制 GC（可选）
            import gc
            gc.collect()

    def should_unload(self) -> bool:
        """检查是否应该卸载"""
        if self._model is None:
            return False
        idle_time = time.monotonic() - self._last_used
        return idle_time > self._idle_timeout

    @property
    def is_loaded(self) -> bool:
        return self._model is not None


class ModelManager:
    """全局模型管理器"""

    def __init__(self, check_interval: float = 60.0):
        self._slots: dict[str, ModelSlot] = {}
        self._check_interval = check_interval
        self._running = False

    def register(
        self,
        name: str,
        loader: Callable[[], Any],
        idle_timeout: float = 300.0,
    ) -> None:
        """注册一个模型"""
        self._slots[name] = ModelSlot(name, loader, idle_timeout)
        logger.info("注册模型: %s (idle_timeout=%.0fs)", name, idle_timeout)

    def get(self, name: str) -> Any:
        """获取模型（自动加载）"""
        if name not in self._slots:
            raise KeyError(f"未注册的模型: {name}")
        return self._slots[name].get()

    def unload(self, name: str) -> None:
        """手动卸载模型"""
        if name in self._slots:
            self._slots[name].unload()

    def unload_all(self) -> None:
        """卸载所有模型"""
        for slot in self._slots.values():
            slot.unload()

    async def start_monitor(self) -> None:
        """启动后台监控任务"""
        self._running = True
        logger.info("模型监控器已启动 (check_interval=%.0fs)", self._check_interval)

        while self._running:
            await asyncio.sleep(self._check_interval)

            for slot in self._slots.values():
                if slot.should_unload():
                    logger.info(
                        "模型 %s 空闲超时，自动卸载",
                        slot.name,
                    )
                    slot.unload()

    def stop_monitor(self) -> None:
        """停止监控"""
        self._running = False


# 全局单例
_manager = ModelManager()


def get_manager() -> ModelManager:
    """获取全局模型管理器"""
    return _manager
```

---

**修改**: `ai-sidecar/dispatcher.py`

```python
from model_manager import get_manager

class Dispatcher:
    def __init__(self) -> None:
        # 注册所有模型到管理器
        manager = get_manager()

        manager.register(
            "ocr",
            loader=self._create_ocr_worker,
            idle_timeout=300.0,  # 5 分钟
        )

        manager.register(
            "embedding",
            loader=self._create_embed_worker,
            idle_timeout=600.0,  # 10 分钟（Embedding 加载慢）
        )

        # ASR/VLM 类似...

    def _get_ocr_worker(self):
        """从管理器获取 OCR Worker"""
        return get_manager().get("ocr")

    def _get_embed_worker(self):
        """从管理器获取 Embedding Worker"""
        return get_manager().get("embedding")

    def _create_ocr_worker(self):
        """工厂方法：创建 OCR Worker"""
        from ocr.worker import OcrWorker
        from ocr.engine import OcrEngine
        return OcrWorker(engine=OcrEngine.create_default())

    def _create_embed_worker(self):
        """工厂方法：创建 Embedding Worker"""
        from embedding.worker import EmbedWorker
        from embedding.model import EmbeddingModel
        return EmbedWorker(model=EmbeddingModel.create_default())
```

---

**修改**: `ai-sidecar/main.py` (假设存在)

```python
import asyncio
from model_manager import get_manager

async def main():
    # 启动模型监控器
    manager = get_manager()
    monitor_task = asyncio.create_task(manager.start_monitor())

    # 启动 IPC 服务器
    # ...

    try:
        await asyncio.gather(monitor_task, ipc_server_task)
    except KeyboardInterrupt:
        manager.stop_monitor()
        manager.unload_all()
```

---

### 方案 2: 内存压力检测（配合方案 1）

当系统内存不足时，主动卸载最久未使用的模型。

```python
import psutil

class ModelManager:
    def check_memory_pressure(self) -> None:
        """检查内存压力，必要时卸载模型"""
        mem = psutil.virtual_memory()

        # 可用内存 < 1GB，触发清理
        if mem.available < 1024 * 1024 * 1024:
            logger.warning(
                "内存不足 (可用: %.1f GB)，开始卸载模型",
                mem.available / 1024 / 1024 / 1024,
            )

            # 按最后使用时间排序
            slots = sorted(
                [s for s in self._slots.values() if s.is_loaded],
                key=lambda s: s._last_used,
            )

            # 卸载最久未使用的模型
            for slot in slots[:2]:  # 最多卸载 2 个
                slot.unload()
```

---

### 方案 3: 模型量化（长期优化）

使用量化模型减少内存占用：

| 模型 | 原始大小 | INT8 量化 | 节省 |
|------|----------|-----------|------|
| BGE-M3 | 2.3GB | ~600MB | -74% |
| PaddleOCR | 200MB | ~50MB | -75% |

**实现**:
```python
# 使用 ONNX Runtime 量化
from optimum.onnxruntime import ORTModelForFeatureExtraction

model = ORTModelForFeatureExtraction.from_pretrained(
    "BAAI/bge-m3",
    export=True,
    provider="CPUExecutionProvider",
)
```

---

## 实施优先级

| 优先级 | 方案 | 预期效果 | 工作量 |
|--------|------|----------|--------|
| P0 | 方案 1: 空闲超时卸载 | 内存 -80% | 4 小时 |
| P1 | 方案 2: 内存压力检测 | 避免 OOM | 2 小时 |
| P2 | 方案 3: 模型量化 | 内存 -70% | 2 天 |

---

## 预期效果

### 优化前
- 启动后首次 OCR: 200MB
- 首次 Embedding: +2.3GB = 2.5GB
- **常驻内存: 2.5GB（永不释放）**

### 优化后（方案 1）
- 启动: 50MB（仅 Python 运行时）
- 使用 OCR: +200MB
- 5 分钟后自动卸载: -200MB
- 使用 Embedding: +2.3GB
- 10 分钟后自动卸载: -2.3GB
- **平均内存: < 300MB**

### 优化后（方案 1 + 3）
- 使用量化模型
- **平均内存: < 100MB**
- **峰值内存: < 800MB**

---

## 总结

**核心问题**: 模型加载后永不释放，导致内存持续占用

**解决方案**:
1. ✅ 实现空闲超时自动卸载（5-10 分钟）
2. ✅ 添加内存压力检测
3. ✅ 长期使用量化模型

**预期改善**:
- 内存占用从 2.5GB 降至 < 300MB（-88%）
- 避免系统 swap 和卡顿
- 用户体验显著提升
