"""
闲时计算系统集成示例

演示如何将闲时计算系统集成到 WorkBuddy AI Sidecar 中。
"""

import asyncio
import logging
from pathlib import Path

from idle_compute import (
    IdleDetector,
    TaskScheduler,
    ModelManager,
    IdleComputeEngine,
    Task,
    TaskType,
    TaskPriority,
    ModelType,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ── 模型加载函数 ──────────────────────────────────────────────────────

def load_ocr_model():
    """加载 OCR 模型（PaddleOCR INT8）"""
    logger.info("加载 PaddleOCR 模型...")
    # 实际实现：
    # from paddleocr import PaddleOCR
    # return PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=False)

    # 模拟加载
    import time
    time.sleep(1)
    return {"type": "ocr", "model": "paddleocr-int8"}


def load_embedding_model():
    """加载 Embedding 模型（BGE-M3 ONNX INT8）"""
    logger.info("加载 BGE-M3 Embedding 模型...")
    # 实际实现：
    # from optimum.onnxruntime import ORTModelForFeatureExtraction
    # return ORTModelForFeatureExtraction.from_pretrained("./bge-m3-int8")

    # 模拟加载
    import time
    time.sleep(3)
    return {"type": "embedding", "model": "bge-m3-int8"}


def load_llm_model():
    """加载 LLM 模型（Qwen2.5 3B）"""
    logger.info("加载 Qwen2.5 3B 模型...")
    # 实际实现：通过 Ollama HTTP API，不需要直接加载
    # 这里只是占位符
    return {"type": "llm", "model": "qwen2.5:3b"}


def load_asr_model():
    """加载 ASR 模型（Whisper Tiny Q5）"""
    logger.info("加载 Whisper Tiny 模型...")
    # 实际实现：
    # from whispercpp import Whisper
    # return Whisper.from_pretrained("tiny-q5_1")

    # 模拟加载
    import time
    time.sleep(2)
    return {"type": "asr", "model": "whisper-tiny-q5"}


def load_vlm_model():
    """加载 VLM 模型（MiniCPM-V Q2_K）"""
    logger.info("加载 MiniCPM-V 模型...")
    # 实际实现：通过 Ollama
    # 模拟加载
    import time
    time.sleep(5)
    return {"type": "vlm", "model": "minicpm-v-q2"}


# ── 主程序 ────────────────────────────────────────────────────────────

async def main():
    """主程序"""
    logger.info("=" * 60)
    logger.info("WorkBuddy 闲时计算系统启动")
    logger.info("=" * 60)

    # 1. 创建闲时检测器
    idle_detector = IdleDetector(
        cpu_threshold=20.0,      # CPU < 20%
        memory_threshold=70.0,   # 内存 < 70%
        stable_duration=60,      # 稳定 1 分钟
        min_interval=3600,       # 1 小时执行 1 次
        require_power=True,      # 需要充电
    )
    logger.info("✓ 闲时检测器已创建")

    # 2. 创建任务调度器
    task_scheduler = TaskScheduler(max_queue_size=1000)
    logger.info("✓ 任务调度器已创建")

    # 3. 创建模型管理器
    model_manager = ModelManager(max_concurrent_models=2)
    logger.info("✓ 模型管理器已创建")

    # 4. 注册模型
    model_manager.register(
        ModelType.OCR,
        name="PaddleOCR-INT8",
        loader=load_ocr_model,
        memory_mb=50,
        keep_loaded=True,  # OCR 常驻内存
    )

    model_manager.register(
        ModelType.EMBEDDING,
        name="BGE-M3-INT8",
        loader=load_embedding_model,
        memory_mb=650,
        keep_loaded=False,  # 闲时加载
    )

    model_manager.register(
        ModelType.LLM,
        name="Qwen2.5-3B",
        loader=load_llm_model,
        memory_mb=2500,
        keep_loaded=False,  # 按需加载
    )

    model_manager.register(
        ModelType.ASR,
        name="Whisper-Tiny-Q5",
        loader=load_asr_model,
        memory_mb=80,
        keep_loaded=False,  # 闲时加载
    )

    model_manager.register(
        ModelType.VLM,
        name="MiniCPM-V-Q2",
        loader=load_vlm_model,
        memory_mb=3000,
        keep_loaded=False,  # 闲时加载
    )
    logger.info("✓ 已注册 5 个模型")

    # 5. 创建闲时计算引擎
    engine = IdleComputeEngine(
        idle_detector=idle_detector,
        task_scheduler=task_scheduler,
        model_manager=model_manager,
    )
    logger.info("✓ 闲时计算引擎已创建")

    # 6. 启动引擎
    await engine.start()

    # 7. 模拟提交任务
    logger.info("\n" + "=" * 60)
    logger.info("模拟提交任务")
    logger.info("=" * 60)

    # 提交一些闲时任务
    for i in range(10):
        task = Task(
            task_id=f"embed-{i}",
            task_type=TaskType.EMBEDDING,
            priority=TaskPriority.IDLE_HIGH,
            payload={"capture_id": i, "text": f"测试文本 {i}"}
        )
        task_scheduler.submit_task(task)

    for i in range(5):
        task = Task(
            task_id=f"vlm-{i}",
            task_type=TaskType.VLM,
            priority=TaskPriority.IDLE_LOW,
            payload={"capture_id": i, "image_path": f"/path/to/image-{i}.jpg"}
        )
        task_scheduler.submit_task(task)

    logger.info("✓ 已提交 15 个闲时任务")

    # 8. 运行一段时间
    logger.info("\n" + "=" * 60)
    logger.info("系统运行中...")
    logger.info("=" * 60)

    try:
        # 每 30 秒打印一次状态
        for _ in range(10):  # 运行 5 分钟
            await asyncio.sleep(30)

            # 打印状态
            logger.info("\n" + "-" * 60)
            logger.info("系统状态:")
            logger.info("-" * 60)

            # 闲时检测器状态
            idle_status = idle_detector.get_status()
            logger.info("闲时检测器:")
            logger.info("  CPU: %.1f%% (阈值: %.1f%%, OK: %s)",
                       idle_status['cpu_usage'],
                       idle_detector.cpu_threshold,
                       idle_status['cpu_ok'])
            logger.info("  内存: %.1f%% (阈值: %.1f%%, OK: %s)",
                       idle_status['memory_usage'],
                       idle_detector.memory_threshold,
                       idle_status['memory_ok'])
            logger.info("  充电: %s", idle_status['on_power'])
            logger.info("  稳定时长: %.0f/%.0f 秒",
                       idle_status['stable_elapsed'],
                       idle_status['stable_required'])
            logger.info("  距离下次执行: %d 秒",
                       idle_status['time_until_next'])

            # 任务调度器状态
            task_stats = task_scheduler.get_stats()
            logger.info("任务调度器:")
            logger.info("  总提交: %d", task_stats['total_submitted'])
            logger.info("  已完成: %d", task_stats['completed'])
            logger.info("  失败: %d", task_stats['failed'])
            logger.info("  待处理: %d (闲时: %d)",
                       task_stats['total_pending'],
                       task_stats['pending_idle'])

            # 模型管理器状态
            model_status = model_manager.get_status()
            logger.info("模型管理器:")
            logger.info("  已加载: %d/%d",
                       model_status['loaded_count'],
                       model_status['total_count'])
            logger.info("  内存占用: %d MB",
                       model_status['total_memory_mb'])

    except KeyboardInterrupt:
        logger.info("\n收到中断信号")

    finally:
        # 9. 停止引擎
        logger.info("\n" + "=" * 60)
        logger.info("正在停止系统...")
        logger.info("=" * 60)
        await engine.stop()
        logger.info("✓ 系统已停止")


if __name__ == "__main__":
    asyncio.run(main())
