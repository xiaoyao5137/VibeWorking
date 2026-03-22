"""
向量存储管理器

负责将向量写入 Qdrant 和 SQLite vector_index 表
"""

import logging
import sqlite3
import time
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class VectorStorage:
    """向量存储管理器"""
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        qdrant_path: Optional[str] = None,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
    ):
        """
        初始化向量存储

        Args:
            db_path: SQLite 数据库路径
            qdrant_path: Qdrant 本地存储路径（优先使用）
            qdrant_host: Qdrant 服务地址
            qdrant_port: Qdrant 服务端口
        """
        self.db_path = db_path or str(Path.home() / ".memory-bread" / "memory-bread.db")
        self.qdrant_path = qdrant_path
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self._qdrant_client = None
        self._collection_name = "memory_bread_captures"

        logger.info(f"VectorStorage 初始化: db={self.db_path}, qdrant_path={qdrant_path}")
    
    def _get_qdrant_client(self):
        """懒加载 Qdrant 客户端"""
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams

                # 使用统一的 Qdrant 本地路径
                qdrant_path = Path.home() / ".qdrant"
                qdrant_path.mkdir(parents=True, exist_ok=True)

                logger.info(f"使用 Qdrant 本地模式: {qdrant_path}")
                self._qdrant_client = QdrantClient(path=str(qdrant_path))

                # 主进程/检索器已占用本地目录时，后台向量化降级为仅写 SQLite，不阻断知识提炼
                # 这里保留客户端初始化逻辑；失败时由 store_vector() 做降级处理

                # 确保集合存在
                collections = self._qdrant_client.get_collections().collections
                collection_names = [c.name for c in collections]
                
                if self._collection_name not in collection_names:
                    logger.info(f"创建 Qdrant 集合: {self._collection_name}")
                    self._qdrant_client.create_collection(
                        collection_name=self._collection_name,
                        vectors_config=VectorParams(
                            size=1024,  # bge-m3 维度
                            distance=Distance.COSINE,
                        ),
                    )
                
                logger.info("Qdrant 客户端已连接")
            except Exception as e:
                logger.error(f"连接 Qdrant 失败: {e}")
                self._qdrant_client = None
        
        return self._qdrant_client
    
    def store_vector(
        self,
        capture_id: int,
        text: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        存储向量到 Qdrant 和 SQLite
        
        Args:
            capture_id: 采集记录 ID
            text: 原始文本
            vector: 向量数据
            metadata: 额外元数据（app_name, timestamp 等）
            
        Returns:
            是否成功
        """
        try:
            # 1. 生成 point_id
            point_id = str(uuid.uuid4())
            
            # 2. 写入 Qdrant
            qdrant_client = self._get_qdrant_client()
            if qdrant_client:
                from qdrant_client.models import PointStruct
                
                payload = {
                    "capture_id": capture_id,
                    "text": text[:500],  # 限制长度
                    "timestamp": metadata.get("timestamp") if metadata else None,
                    "app_name": metadata.get("app_name") if metadata else None,
                }
                
                point = PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
                
                qdrant_client.upsert(
                    collection_name=self._collection_name,
                    points=[point],
                )
                
                logger.debug(f"向量已写入 Qdrant: {point_id}")
            else:
                logger.warning("Qdrant 不可用，降级为仅写 SQLite vector_index")

            # 3. 写入 SQLite vector_index 表
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT INTO vector_index 
                (capture_id, qdrant_point_id, chunk_index, chunk_text, model_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    capture_id,
                    point_id,
                    0,  # chunk_index
                    text,
                    "bge-m3",
                    int(metadata.get("timestamp", 0)) if metadata else 0,
                ),
            )
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ 向量存储完成: capture_id={capture_id}, point_id={point_id}")
            return True
        
        except Exception as e:
            logger.error(f"❌ 向量存储失败: {e}", exc_info=True)
            return False


# 全局单例
_vector_storage = None


def get_vector_storage() -> VectorStorage:
    """获取全局向量存储单例"""
    global _vector_storage
    if _vector_storage is None:
        _vector_storage = VectorStorage()
    return _vector_storage
