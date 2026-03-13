#!/usr/bin/env python3
"""
批量向量化测试脚本
"""
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from background_processor import BackgroundProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    db_path = str(Path.home() / ".workbuddy" / "workbuddy.db")

    logger.info("=" * 60)
    logger.info("开始批量向量化测试")
    logger.info("=" * 60)

    processor = BackgroundProcessor(
        db_path=db_path,
        interval=30,
        batch_size=20  # 每批处理 20 条
    )

    # 手动运行一次处理
    logger.info("执行一次向量化处理...")
    processed = await processor._process_batch()
    logger.info(f"本次处理了 {processed} 条记录")

    logger.info("=" * 60)
    logger.info("向量化测试完成")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
