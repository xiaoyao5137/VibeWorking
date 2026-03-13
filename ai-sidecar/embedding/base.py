"""
Embedding 后端抽象基类与数据类型
"""

from __future__ import annotations

from abc       import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EmbeddingVector:
    """单条文本的 Embedding 结果"""
    text:   str
    vector: list[float] = field(default_factory=list)

    @property
    def dimension(self) -> int:
        return len(self.vector)


class EmbeddingBackend(ABC):
    """Embedding 后端接口（所有后端必须实现）"""

    @abstractmethod
    def is_available(self) -> bool:
        """当前环境是否可用（依赖库已安装且可加载）"""

    @abstractmethod
    def encode(self, texts: list[str]) -> list[EmbeddingVector]:
        """将文本列表编码为向量列表（顺序与输入一致）"""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """后端使用的模型名称"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
