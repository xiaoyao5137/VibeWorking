"""
检索器模块

提供多种检索策略：
- VectorRetriever: Qdrant 向量检索
- Fts5Retriever: SQLite FTS5 全文检索
- KnowledgeFts5Retriever: 知识库 FTS5 检索
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """检索到的文本片段"""
    capture_id: int
    text: str
    score: float = 0.0
    source: str = "unknown"  # "vector" / "fts5" / "knowledge"
    metadata: dict = None  # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class VectorRetriever:
    """Qdrant 向量检索器"""

    def __init__(
        self,
        collection: str = "memory_bread_captures",
        host: Optional[str] = None,
        port: Optional[int] = None,
        qdrant_path: Optional[str] = None,
    ):
        self.collection = collection
        self.host = host
        self.port = port
        self.qdrant_path = qdrant_path
        self._client = None

    def _get_client(self):
        """懒加载 Qdrant 客户端"""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                # 优先使用本地模式
                if self.qdrant_path:
                    self._client = QdrantClient(path=self.qdrant_path)
                    logger.info(f"Qdrant 本地模式已连接: {self.qdrant_path}")
                else:
                    self._client = QdrantClient(host=self.host or "localhost", port=self.port or 6333)
                    logger.info(f"Qdrant 客户端已连接: {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"连接 Qdrant 失败: {e}")
                self._client = None
        return self._client
    
    def is_available(self) -> bool:
        """检查 Qdrant 是否可用"""
        return self._get_client() is not None

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        score_threshold: float = 0.3,
    ) -> list[RetrievedChunk]:
        """
        向量相似度搜索
        
        Args:
            query_vector: 查询向量
            top_k: 返回结果数量
            score_threshold: 相似度阈值
            
        Returns:
            检索结果列表
        """
        if not query_vector:
            return []
        
        client = self._get_client()
        if not client:
            logger.warning("Qdrant 不可用，跳过向量检索")
            return []
        
        try:
            from qdrant_client.models import QueryRequest, VectorInput

            results = client.query_points(
                collection_name=self.collection,
                query=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
            ).points

            chunks = []
            for hit in results:
                chunks.append(RetrievedChunk(
                    capture_id=hit.payload.get("capture_id", 0),
                    text=hit.payload.get("text", ""),
                    score=hit.score,
                    source="vector",
                ))

            logger.debug(f"向量检索返回 {len(chunks)} 条结果")
            return chunks
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []


class Fts5Retriever:
    """SQLite FTS5 全文检索器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[RetrievedChunk]:
        """
        FTS5 全文检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # FTS5 全文搜索
            cursor.execute(
                """
                SELECT
                    c.id as capture_id,
                    c.ocr_text as text,
                    fts.rank as score
                FROM captures_fts fts
                JOIN captures c ON fts.rowid = c.id
                WHERE captures_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, top_k),
            )
            
            chunks = []
            for row in cursor.fetchall():
                chunks.append(RetrievedChunk(
                    capture_id=row["capture_id"],
                    text=row["text"],
                    score=abs(row["score"]),  # FTS5 rank 是负数
                    source="fts5",
                ))
            
            conn.close()
            logger.debug(f"FTS5 检索返回 {len(chunks)} 条结果")
            return chunks
        except Exception as e:
            logger.error(f"FTS5 检索失败: {e}")
            return []


class KnowledgeFts5Retriever:
    """知识库 FTS5 检索器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[RetrievedChunk]:
        """
        知识库 FTS5 检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 检查 knowledge_fts 表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_fts'"
            )
            if not cursor.fetchone():
                logger.debug("knowledge_fts 表不存在，跳过知识库检索")
                conn.close()
                return []
            
            # 知识库 FTS5 搜索
            cursor.execute(
                """
                SELECT
                    k.capture_id as capture_id,
                    k.summary as text,
                    fts.rank as score
                FROM knowledge_fts fts
                JOIN knowledge_entries k ON fts.rowid = k.id
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, top_k),
            )
            
            chunks = []
            for row in cursor.fetchall():
                chunks.append(RetrievedChunk(
                    capture_id=row["capture_id"],
                    text=row["text"],
                    score=abs(row["score"]),
                    source="knowledge",
                ))
            
            conn.close()
            logger.debug(f"知识库检索返回 {len(chunks)} 条结果")
            return chunks
        except Exception as e:
            logger.error(f"知识库检索失败: {e}")
            return []
