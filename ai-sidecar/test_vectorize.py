#!/usr/bin/env python3
"""
手动触发向量化测试脚本
"""
import asyncio
import logging
from pathlib import Path
from embedding.worker import EmbedWorker
from embedding.model import EmbeddingModel
from embedding.vector_storage import VectorStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    db_path = str(Path.home() / ".memory-bread" / "memory-bread.db")
    qdrant_path = str(Path.home() / ".qdrant")

    logger.info("初始化向量化组件...")
    model = EmbeddingModel.create_default()
    worker = EmbedWorker(model=model)
    storage = VectorStorage(
        db_path=db_path,
        qdrant_path=qdrant_path,
        collection_name="memory_bread_captures"
    )

    logger.info("开始批量向量化...")
    # 处理前 50 条记录作为测试
    count = await worker.process_batch(db_path, storage, batch_size=50)
    logger.info(f"向量化完成，处理了 {count} 条记录")

if __name__ == "__main__":
    asyncio.run(main())
