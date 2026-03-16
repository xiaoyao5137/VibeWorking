"""
后台任务处理器 - 自动处理向量化和知识提炼

定期扫描数据库中未处理的采集记录，执行：
1. 向量化（Embedding）
2. 知识提炼（Knowledge Extraction）
"""

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

from knowledge.fragment_grouper import FragmentGrouper

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
        """获取未处理的采集记录（按时间升序，用于分组）"""
        cursor = conn.cursor()
        # knowledge_id IS NULL 表示尚未被合并进任何工作片段
        cursor.execute("""
            SELECT c.id, c.ts, c.app_name, c.win_title, c.ocr_text, c.ax_text
            FROM captures c
            WHERE (c.ocr_text IS NOT NULL AND c.ocr_text != '')
              AND c.knowledge_id IS NULL
              AND c.is_sensitive = 0
            ORDER BY c.ts ASC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [
            {
                'id': r[0], 'ts': r[1], 'app_name': r[2],
                'window_title': r[3], 'ocr_text': r[4], 'ax_text': r[5],
            }
            for r in rows
        ]

    def _get_fragment_grouper(self):
        """懒加载 FragmentGrouper"""
        if not hasattr(self, '_fragment_grouper'):
            from knowledge.fragment_grouper import FragmentGrouper
            # 复用已有的 embedding model（如果已初始化）
            embed_model = self._embed_worker.model if self._embed_worker else None
            self._fragment_grouper = FragmentGrouper(embedding_model=embed_model)
            logger.info("FragmentGrouper 已初始化")
        return self._fragment_grouper

    def _save_knowledge(self, conn: sqlite3.Connection, knowledge: dict) -> int:
        """保存 knowledge 条目，返回新插入的 id"""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO knowledge_entries
            (capture_id, summary, overview, details, entities, category, importance,
             occurrence_count, capture_ids, start_time, end_time, duration_minutes,
             frag_app_name, frag_win_title)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            # capture_id 用 capture_ids 中的第一个（向后兼容）
            json.loads(knowledge.get('capture_ids', '[0]'))[0],
            knowledge.get('overview', ''),   # summary 字段保持向后兼容
            knowledge.get('overview', ''),
            knowledge.get('details', ''),
            knowledge.get('entities', '[]'),
            knowledge.get('category', '其他'),
            knowledge.get('importance', 3),
            knowledge.get('occurrence_count', 1),
            knowledge.get('capture_ids'),
            knowledge.get('start_time'),
            knowledge.get('end_time'),
            knowledge.get('duration_minutes'),
            knowledge.get('frag_app_name'),
            knowledge.get('frag_win_title'),
        ))
        conn.commit()
        return cursor.lastrowid

    def _mark_captures_processed(
        self, conn: sqlite3.Connection, capture_ids: list[int], knowledge_id: int
    ):
        """标记 captures 已被合并进 knowledge"""
        placeholders = ','.join('?' * len(capture_ids))
        conn.execute(
            f"UPDATE captures SET knowledge_id = ? WHERE id IN ({placeholders})",
            [knowledge_id] + capture_ids,
        )
        conn.commit()

    async def _process_capture_group(self, group: list[dict]):
        """将一组 captures 合并提炼为一个 knowledge 条目"""
        try:
            extractor = self._get_knowledge_extractor()
            knowledge = extractor.extract_merged(captures=group)

            if not knowledge:
                logger.debug(f"片段无价值，跳过 ({len(group)} 条 captures)")
                return False

            conn = sqlite3.connect(self.db_path)
            knowledge_id = self._save_knowledge(conn, knowledge)
            capture_ids = [c['id'] for c in group]
            self._mark_captures_processed(conn, capture_ids, knowledge_id)
            conn.close()

            logger.info(
                f"✅ 片段提炼完成: {len(group)} captures → knowledge_id={knowledge_id}, "
                f"时长={knowledge.get('duration_minutes')}分钟"
            )
            return True

        except Exception as e:
            logger.error(f"片段提炼异常: {e}")
            return False

    async def _process_vectorization_batch(self, group: list[dict]):
        """对一组 captures 批量向量化"""
        for capture in group:
            ocr_text = capture.get('ocr_text', '')
            if ocr_text:
                await self._process_vectorization(capture['id'], ocr_text)
                await asyncio.sleep(0.1)
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
        """处理一批未处理的记录（基于语义分组）"""
        try:
            conn = sqlite3.connect(self.db_path)
            captures = self._get_unprocessed_captures(conn, self.batch_size)
            conn.close()

            if not captures:
                return 0

            # 数据太少时等待更多积累，避免切断进行中的任务
            if len(captures) < FragmentGrouper.MIN_GROUP_WAIT:
                logger.debug(f"captures 数量不足 ({len(captures)})，等待积累")
                return 0

            logger.info(f"📦 发现 {len(captures)} 条待处理 captures，开始语义分组")

            # 语义分组
            grouper = self._get_fragment_grouper()
            groups = grouper.group_captures(captures)

            # 最后一组可能是进行中的任务，暂不处理
            groups_to_process = groups[:-1] if len(groups) > 1 else []

            if not groups_to_process:
                logger.debug("所有 captures 可能属于进行中的任务，等待下一轮")
                return 0

            logger.info(f"分组结果: {len(captures)} captures → {len(groups)} 组，本轮处理 {len(groups_to_process)} 组")

            processed = 0
            for group in groups_to_process:
                # 1. 向量化（每条 capture 独立向量化，用于 RAG 检索）
                await self._process_vectorization_batch(group)

                # 2. 合并提炼为一个 knowledge 片段
                if await self._process_capture_group(group):
                    processed += 1

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
