"""
RagPipeline — 完整 RAG 查询流水线

流程：
  Query → Embedding → [Qdrant 语义 + FTS5 关键词] → RRF 合并 → Prompt 组装 → LLM 推理 → 结果
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from embedding.model import EmbeddingModel

from .llm.base import LlmBackend
from .reranker import reciprocal_rank_fusion
from .retriever import (
    Fts5Retriever,
    KnowledgeFts5Retriever,
    RetrievedChunk,
    VectorRetriever,
    VectorSearchFilter,
)

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

    answer: str
    contexts: list[RetrievedChunk] = field(default_factory=list)
    model: str = ""
    tokens: int = 0


@dataclass
class QueryIntent:
    start_ts: int | None = None
    end_ts: int | None = None
    observed_start_ts: int | None = None
    observed_end_ts: int | None = None
    event_start_ts: int | None = None
    event_end_ts: int | None = None
    entity_terms: list[str] = field(default_factory=list)
    app_names: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    category: str | None = None
    target_time_semantics: str = "either"
    activity_types: list[str] = field(default_factory=list)
    content_origins: list[str] = field(default_factory=list)
    history_view: bool | None = None
    is_self_generated: bool | None = None
    evidence_strengths: list[str] = field(default_factory=list)


class RagPipeline:
    """
    RAG 流水线编排器。

    所有依赖（embedding_model, vector_retriever, fts5_retriever, llm）均通过
    构造函数注入，支持完整的 Mock 替换以便测试。
    """

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        vector_retriever: VectorRetriever,
        fts5_retriever: Fts5Retriever,
        llm: LlmBackend,
        knowledge_retriever: KnowledgeFts5Retriever | None = None,
        top_k: int = 5,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._embed = embedding_model
        self._vector = vector_retriever
        self._fts5 = fts5_retriever
        self._knowledge = knowledge_retriever
        self._llm = llm
        self._top_k = top_k
        self._system = system_prompt

    def query(self, user_query: str, top_k: int | None = None) -> RagResult:
        """执行完整 RAG 查询，返回 LLM 答案及引用的上下文片段。"""
        effective_top_k = top_k or self._top_k
        intent = self._parse_query_intent(user_query)

        query_vector: list[float] = []
        try:
            embed_results = self._embed.encode([user_query])
            if embed_results:
                query_vector = embed_results[0].vector
        except Exception as exc:
            logger.warning("Query embedding 失败，跳过语义检索: %s", exc)

        knowledge_results = self._knowledge.search(
            user_query,
            top_k=effective_top_k * 2,
            start_ts=intent.start_ts,
            end_ts=intent.end_ts,
            entity_terms=intent.entity_terms,
            observed_start_ts=intent.observed_start_ts,
            observed_end_ts=intent.observed_end_ts,
            event_start_ts=intent.event_start_ts,
            event_end_ts=intent.event_end_ts,
            activity_types=intent.activity_types or None,
            content_origins=intent.content_origins or None,
            history_view=intent.history_view,
            is_self_generated=intent.is_self_generated,
            evidence_strengths=intent.evidence_strengths or None,
        ) if self._knowledge else []
        vector_results = (
            self._vector.search(
                query_vector,
                top_k=effective_top_k * 3,
                filters=VectorSearchFilter(
                    start_ts=intent.start_ts,
                    end_ts=intent.end_ts,
                    observed_start_ts=intent.observed_start_ts,
                    observed_end_ts=intent.observed_end_ts,
                    event_start_ts=intent.event_start_ts,
                    event_end_ts=intent.event_end_ts,
                    source_types=["knowledge"],
                    app_names=intent.app_names or intent.entity_terms or None,
                    category=intent.category,
                    activity_types=intent.activity_types or None,
                    content_origins=intent.content_origins or None,
                    history_view=intent.history_view,
                    is_self_generated=intent.is_self_generated,
                    evidence_strengths=intent.evidence_strengths or None,
                ),
            )
            if query_vector else []
        )

        merged = reciprocal_rank_fusion(
            [knowledge_results, vector_results],
            top_k=max(effective_top_k * 2, 6),
        )
        selected_contexts = self._select_contexts(merged, effective_top_k)

        context_text = self._build_context(selected_contexts)
        prompt = f"工作记录上下文：\n{context_text}\n\n用户问题：{user_query}"

        llm_resp = self._llm.complete(prompt, system=self._system)

        return RagResult(
            answer=llm_resp.text,
            contexts=selected_contexts,
            model=llm_resp.model,
            tokens=llm_resp.tokens,
        )

    @staticmethod
    def _build_context(chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "（无相关工作记录）"
        parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk.metadata.get("source_type") or chunk.source
            observed_at = chunk.metadata.get("observed_at")
            event_start = chunk.metadata.get("event_time_start")
            event_end = chunk.metadata.get("event_time_end")
            history_view = chunk.metadata.get("history_view")
            activity_type = chunk.metadata.get("activity_type")
            content_origin = chunk.metadata.get("content_origin")
            prefix: list[str] = [f"[{i}][{source}]"]
            if observed_at:
                prefix.append(f"看到时间={_format_ts(observed_at)}")
            if event_start or event_end:
                if event_start and event_end and event_start != event_end:
                    prefix.append(f"事件时间={_format_ts(event_start)}~{_format_ts(event_end)}")
                else:
                    prefix.append(f"事件时间={_format_ts(event_start or event_end)}")
            if history_view:
                prefix.append("历史回看")
            if activity_type:
                prefix.append(f"活动={activity_type}")
            if content_origin:
                prefix.append(f"来源={content_origin}")
            text = chunk.text[:_MAX_CHUNK_LEN]
            parts.append(f"{' '.join(prefix)} {text}")
        return "\n\n".join(parts)

    @staticmethod
    def _select_contexts(chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        selected_keys: set[str] = set()

        for chunk in chunks:
            if len(selected) >= top_k:
                break
            source_type = chunk.metadata.get("source_type") or chunk.source
            if source_type != "knowledge":
                continue
            doc_key = chunk.doc_key or chunk.metadata.get("doc_key")
            if not doc_key or doc_key in selected_keys:
                continue
            selected.append(chunk)
            selected_keys.add(doc_key)

        return selected

    @staticmethod
    def _parse_query_intent(user_query: str) -> QueryIntent:
        lowered = user_query.lower()
        now_ms = int(time.time() * 1000)
        start_ts: int | None = None
        end_ts: int | None = now_ms
        observed_start_ts: int | None = None
        observed_end_ts: int | None = None
        event_start_ts: int | None = None
        event_end_ts: int | None = None
        target_time_semantics = "either"

        if "最近" in user_query:
            start_ts = now_ms - 7 * 24 * 60 * 60 * 1000
            observed_start_ts = start_ts
            observed_end_ts = end_ts
        elif "今天" in user_query:
            start_ts = _day_start_ms(0)
            observed_start_ts = start_ts
            observed_end_ts = end_ts
        elif "昨天" in user_query:
            start_ts = _day_start_ms(-1)
            end_ts = _day_start_ms(0) - 1
            observed_start_ts = start_ts
            observed_end_ts = end_ts
            event_start_ts = start_ts
            event_end_ts = end_ts
        elif "本周" in user_query:
            start_ts = _week_start_ms()
            observed_start_ts = start_ts
            observed_end_ts = end_ts

        entity_terms = _extract_query_terms(user_query)
        app_names = [term for term in entity_terms if any(ch.isascii() for ch in term)]

        source_types: list[str] = []
        if any(token in user_query for token in ("知识", "总结", "结论", "概述")):
            source_types.append("knowledge")
        if any(token in user_query for token in ("原文", "记录", "截图", "窗口", "应用")):
            source_types.append("capture")

        category = None
        if "会议" in user_query:
            category = "会议"
        elif "文档" in user_query:
            category = "文档"
        elif "代码" in user_query:
            category = "代码"
        elif "聊天" in user_query:
            category = "聊天"

        activity_types: list[str] = []
        content_origins: list[str] = []
        history_view: bool | None = None
        is_self_generated: bool | None = False
        evidence_strengths: list[str] = []

        asks_ai = any(token in lowered for token in ("gemini", "claude", "chatgpt", "ai")) and any(
            token in user_query for token in ("问", "提问", "聊", "对话")
        )
        asks_history = any(token in user_query for token in ("历史消息", "历史记录", "历史对话", "回看", "回顾"))
        asks_daily_summary = "今天" in user_query and any(token in user_query for token in ("做了什么", "干了什么", "做过什么"))

        if asks_ai:
            target_time_semantics = "observed"
            activity_types = ["ask_ai"]
            history_view = False
            evidence_strengths = ["medium", "high"]
        elif asks_history:
            target_time_semantics = "observed"
            activity_types = ["reviewing_history", "chat", "reading"]
            content_origins = ["historical_content"]
            history_view = True
            evidence_strengths = ["medium", "high"]
        elif asks_daily_summary:
            target_time_semantics = "observed"
            history_view = False
            activity_types = ["coding", "reading", "meeting", "chat", "ask_ai"]
            evidence_strengths = ["medium", "high"]

        if target_time_semantics == "event" and observed_start_ts is not None:
            observed_start_ts = None
            observed_end_ts = None
        elif target_time_semantics == "observed" and start_ts is not None:
            event_start_ts = None
            event_end_ts = None

        return QueryIntent(
            start_ts=start_ts,
            end_ts=end_ts,
            observed_start_ts=observed_start_ts,
            observed_end_ts=observed_end_ts,
            event_start_ts=event_start_ts,
            event_end_ts=event_end_ts,
            entity_terms=entity_terms,
            app_names=app_names,
            source_types=source_types,
            category=category,
            target_time_semantics=target_time_semantics,
            activity_types=activity_types,
            content_origins=content_origins,
            history_view=history_view,
            is_self_generated=is_self_generated,
            evidence_strengths=evidence_strengths,
        )


def _extract_query_terms(query: str) -> list[str]:
    import re

    tokens = re.findall(r"[A-Za-z0-9.]+|[\u4e00-\u9fff]+", query.lower())
    terms: list[str] = []
    seen: set[str] = set()
    stop_terms = {
        "什么", "怎么", "如何", "为什么", "昨天", "今天", "最近", "本周", "那段",
        "提到", "知识", "总结", "里", "了吗", "是否", "有关", "关于", "做了什么",
        "干了什么", "做过什么", "问了什么", "看了什么", "历史消息", "历史记录", "历史对话",
    }

    def _add(term: str) -> None:
        term = term.strip()
        if len(term) < 2 or term in stop_terms or term in seen:
            return
        seen.add(term)
        terms.append(term)

    for token in tokens:
        if len(token) < 2:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 4:
            for size in (4, 3, 2):
                for i in range(0, len(token) - size + 1):
                    _add(token[i:i + size])
        else:
            _add(token)

    return terms



def _day_start_ms(offset_days: int) -> int:
    now = time.localtime()
    midnight = time.mktime((
        now.tm_year,
        now.tm_mon,
        now.tm_mday,
        0,
        0,
        0,
        now.tm_wday,
        now.tm_yday,
        now.tm_isdst,
    ))
    return int((midnight + offset_days * 24 * 60 * 60) * 1000)



def _week_start_ms() -> int:
    now = time.localtime()
    start_today_ms = _day_start_ms(0)
    return start_today_ms - now.tm_wday * 24 * 60 * 60 * 1000



def _format_ts(ts: int | None) -> str:
    if not ts:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts / 1000))
    except Exception:
        return str(ts)
