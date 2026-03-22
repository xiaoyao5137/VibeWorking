"""
RagPipeline — 完整 RAG 查询流水线

流程：
  Query → Embedding → [Qdrant 语义 + FTS5 关键词] → RRF 合并 → Prompt 组装 → LLM 推理 → 结果
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from embedding.model import EmbeddingModel

from .llm.base  import LlmBackend
from .reranker  import reciprocal_rank_fusion
from .retriever import Fts5Retriever, KnowledgeFts5Retriever, RetrievedChunk, VectorRetriever

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "你是记忆面包，一个本地运行的 AI 工作助手。"
    "根据以下工作记录上下文，简洁、准确地回答用户的问题。"
    "如果上下文中没有相关信息，请直接说明。"
)

_MAX_CHUNK_LEN = 500   # 单个上下文片段最大字符数


@dataclass
class RagResult:
    """RAG 查询结果"""
    answer:   str
    contexts: list[RetrievedChunk] = field(default_factory=list)
    model:    str = ""
    tokens:   int = 0


class RagPipeline:
    """
    RAG 流水线编排器。

    所有依赖（embedding_model, vector_retriever, fts5_retriever, llm）均通过
    构造函数注入，支持完整的 Mock 替换以便测试。
    """

    def __init__(
        self,
        embedding_model:     EmbeddingModel,
        vector_retriever:    VectorRetriever,
        fts5_retriever:      Fts5Retriever,
        llm:                 LlmBackend,
        knowledge_retriever: KnowledgeFts5Retriever | None = None,
        top_k:               int = 5,
        system_prompt:       str = _DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._embed     = embedding_model
        self._vector    = vector_retriever
        self._fts5      = fts5_retriever
        self._knowledge = knowledge_retriever
        self._llm       = llm
        self._top_k     = top_k
        self._system    = system_prompt

    # ── 公共接口 ──────────────────────────────────────────────────────────────

    def query(self, user_query: str) -> RagResult:
        """
        执行完整 RAG 查询，返回 LLM 答案及引用的上下文片段。

        Args:
            user_query: 用户原始问题

        Returns:
            RagResult（answer + contexts + model + tokens）
        """
        # ① Query Embedding（失败时跳过语义检索，降级为纯 FTS5）
        query_vector: list[float] = []
        try:
            embed_results = self._embed.encode([user_query])
            if embed_results:
                query_vector = embed_results[0].vector
        except Exception as exc:
            logger.warning("Query embedding 失败，跳过语义检索: %s", exc)

        # ② 并行检索（FTS5 关键词 + 知识库 + 向量语义）
        fts5_results      = self._fts5.search(user_query, top_k=self._top_k * 2)
        knowledge_results = self._knowledge.search(user_query, top_k=self._top_k * 2) if self._knowledge else []
        vector_results    = (
            self._vector.search(query_vector, top_k=self._top_k * 2)
            if query_vector else []
        )

        # ③ RRF 合并（三路合并）
        merged = reciprocal_rank_fusion(
            [fts5_results, knowledge_results, vector_results],
            top_k=self._top_k,
        )

        # ④ 组装 Prompt
        context_text = self._build_context(merged)
        prompt = f"工作记录上下文：\n{context_text}\n\n用户问题：{user_query}"

        # ⑤ LLM 推理
        llm_resp = self._llm.complete(prompt, system=self._system)

        return RagResult(
            answer   = llm_resp.text,
            contexts = merged,
            model    = llm_resp.model,
            tokens   = llm_resp.tokens,
        )

    # ── 内部 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_context(chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "（无相关工作记录）"
        parts = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.text[:_MAX_CHUNK_LEN]
            parts.append(f"[{i}] {text}")
        return "\n\n".join(parts)
