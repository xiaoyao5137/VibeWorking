"""
Embedding 向量化服务

使用 bge-m3 模型将文本转换为向量
"""

import logging
from typing import List
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """文本向量化服务"""
    
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        """
        初始化 Embedding 服务
        
        Args:
            model_name: 模型名称，默认使用 bge-m3
        """
        self.model_name = model_name
        self.model = None
        logger.info(f"初始化 EmbeddingService，模型: {model_name}")
    
    def load_model(self):
        """延迟加载模型（首次调用时加载）"""
        if self.model is None:
            logger.info(f"正在加载模型 {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            logger.info("模型加载完成")
    
    def encode(self, texts: List[str]) -> List[List[float]]:
        """
        将文本列表转换为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表，每个向量是一个浮点数列表
        """
        self.load_model()
        
        if not texts:
            return []
        
        logger.debug(f"正在向量化 {len(texts)} 条文本")
        
        # sentence-transformers 返回 numpy array
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        
        # 转换为 Python list
        result = [emb.tolist() for emb in embeddings]
        
        logger.debug(f"向量化完成，维度: {len(result[0])}")
        return result
    
    def encode_single(self, text: str) -> List[float]:
        """
        向量化单个文本
        
        Args:
            text: 单个文本
            
        Returns:
            向量（浮点数列表）
        """
        vectors = self.encode([text])
        return vectors[0] if vectors else []


# 全局单例
_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """获取全局 Embedding 服务单例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
