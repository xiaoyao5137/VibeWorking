"""
后台任务处理器 - 自动处理向量化和知识提炼

定期扫描数据库中未处理的采集记录，执行：
1. 向量化（Embedding）
2. 知识提炼（Knowledge Extraction）
"""

import asyncio
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class BackgroundProcessor:
    """后台任务处理器"""

    def __init__(
        self,
        db_path: str,
        interval: int = 30,  # 扫描间隔（秒）
        batch_size: int = 10,  # 每次处理的记录数
    ):
        self.db_path = db_path
        self.interval = interval
        self.batch_size = batch_size
        self.running = False

        # 懒加载 workers
        self._embed_worker = None
        self._knowledge_extractor = None

    def _get_embed_worker(self):
        """懒加载 EmbedWorker"""
        if self._embed_worker is None:
            from embedding.worker import EmbedWorker
            from embedding.model import EmbeddingModel
            self._embed_worker = EmbedWorker(model=EmbeddingModel.create_default())
            logger.info("EmbedWorker 已初始化（后台任务）")
        return self._embed_worker

    def _get_knowledge_extractor(self):
        """懒加载 KnowledgeExtractor V2"""
        if self._knowledge_extractor is None:
            from knowledge.extractor_v2 import KnowledgeExtractorV2
            from embedding.model import EmbeddingModel

            # 加载向量模型用于去重
            embedding_model = EmbeddingModel.create_default()
            self._knowledge_extractor = KnowledgeExtractorV2(embedding_model=embedding_model)
            logger.info("KnowledgeExtractor V2 已初始化（后台任务，支持去重）")
        return self._knowledge_extractor

    def _get_unprocessed_captures(self, conn: sqlite3.Connection, limit: int):
        """获取未向量化的采集记录"""
        cursor = conn.cursor()

        # 查找有 OCR 文本但未向量化的记录
        cursor.execute("""
            SELECT c.id, c.ts, c.app_name, c.win_title, c.ocr_text
            FROM captures c
            LEFT JOIN vector_index v ON c.id = v.capture_id
            WHERE c.ocr_text IS NOT NULL
              AND c.ocr_text != ''
              AND v.capture_id IS NULL
            ORDER BY c.ts DESC
            LIMIT ?
        """, (limit,))

        return cursor.fetchall()

    async def _process_vectorization(self, capture_id: int, ocr_text: str):
        """处理单条记录的向量化"""
        try:
            worker = self._get_embed_worker()

            # 创建 IPC 请求格式
            from workbuddy_ipc import IpcRequest, EmbedRequest

            embed_req = EmbedRequest(
                capture_id=capture_id,
                texts=[ocr_text]  # 注意：texts 是列表
            )

            req = IpcRequest(
                id=f"bg_{capture_id}",
                ts=int(time.time() * 1000),
                task=embed_req
            )
            response = await worker.handle(req)

            if response.status == "ok":
                # 向量化成功后，写入 Qdrant 和 SQLite
                from embedding.vector_storage import get_vector_storage

                vectors = response.result.vectors
                if vectors and len(vectors) > 0:
                    storage = get_vector_storage()
                    success = storage.store_vector(
                        capture_id=capture_id,
                        text=ocr_text,
                        vector=vectors[0],
                        metadata={
                            "timestamp": req.ts,
                        }
                    )

                    if success:
                        logger.info(f"✅ 向量化+存储完成: capture_id={capture_id}")
                        return True
                    else:
                        logger.error(f"❌ 向量存储失败: capture_id={capture_id}")
                        return False
                else:
                    logger.warning(f"⚠️  向量化返回空结果: capture_id={capture_id}")
                    return False
            else:
                logger.error(f"❌ 向量化失败: capture_id={capture_id}, error={response.error}")
                return False

        except Exception as e:
            logger.error(f"❌ 向量化异常: capture_id={capture_id}, error={e}")
            return False

    async def _process_knowledge_extraction(self, capture_data: dict):
        """处理单条记录的知识提炼"""
        try:
            extractor = self._get_knowledge_extractor()

            # 打开数据库连接用于去重
            conn = sqlite3.connect(self.db_path)

            # 使用同步方法提炼（V2 版本）
            knowledge = extractor.extract_sync(capture_data, db_conn=conn)

            if knowledge:
                # 保存到数据库
                cursor = conn.cursor()

                # 支持新旧两种格式
                overview = knowledge.get('overview') or knowledge.get('summary', '')
                details = knowledge.get('details', '')

                cursor.execute("""
                    INSERT INTO knowledge_entries
                    (capture_id, summary, overview, details, entities, category, importance, occurrence_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    capture_data['id'],
                    overview,  # 保持向后兼容
                    overview,
                    details,
                    knowledge.get('entities', '[]'),
                    knowledge.get('category', '其他'),
                    knowledge.get('importance', 3),
                    knowledge.get('occurrence_count', 1)
                ))

                conn.commit()
                conn.close()

                logger.info(f"✅ 知识提炼完成: capture_id={capture_data['id']}, category={knowledge.get('category')}")
                return True
            else:
                conn.close()
                logger.debug(f"⏭️  跳过无价值或重复内容: capture_id={capture_data['id']}")
                return False

        except Exception as e:
            logger.error(f"❌ 知识提炼异常: capture_id={capture_data['id']}, error={e}")
            return False

    async def _process_batch(self):
        """处理一批未处理的记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            records = self._get_unprocessed_captures(conn, self.batch_size)
            conn.close()

            if not records:
                return 0

            logger.info(f"📦 发现 {len(records)} 条待处理记录")

            processed = 0
            for record in records:
                capture_id, ts, app_name, win_title, ocr_text = record

                # 1. 向量化
                if await self._process_vectorization(capture_id, ocr_text):
                    processed += 1

                # 2. 知识提炼
                capture_data = {
                    'id': capture_id,
                    'timestamp': ts,
                    'app_name': app_name,
                    'window_title': win_title,
                    'ocr_text': ocr_text
                }
                await self._process_knowledge_extraction(capture_data)

                # 避免过载
                await asyncio.sleep(0.5)

            return processed

        except Exception as e:
            logger.error(f"批处理异常: {e}")
            return 0

    async def run(self):
        """运行后台处理循环"""
        self.running = True
        logger.info(f"🚀 后台处理器启动 (间隔={self.interval}s, 批量={self.batch_size})")

        while self.running:
            try:
                processed = await self._process_batch()

                if processed > 0:
                    logger.info(f"✅ 本轮处理完成: {processed} 条记录")

                # 等待下一轮
                await asyncio.sleep(self.interval)

            except Exception as e:
                logger.error(f"后台处理循环异常: {e}")
                await asyncio.sleep(self.interval)

    def stop(self):
        """停止后台处理器"""
        logger.info("⏹️  停止后台处理器")
        self.running = False
