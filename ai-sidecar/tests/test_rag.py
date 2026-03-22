"""
RAG 模块测试

测试覆盖：
- RetrievedChunk 数据类属性
- reciprocal_rank_fusion (RRF) 合并逻辑
- RagPipeline.query()（正常 / 无上下文 / embedding 失败降级）
- VectorRetriever.is_available()（不依赖 Qdrant 安装）
- LLM 后端接口验证（MockLlmBackend / OllamaBackend 可用性检测）
"""

from __future__ import annotations

import pytest

from embedding.base  import EmbeddingBackend, EmbeddingVector
from embedding.model import EmbeddingModel
from rag.llm.base    import LlmBackend, LlmResponse
from rag.llm.ollama  import OllamaBackend
from rag.pipeline    import RagPipeline, RagResult
from rag.retriever   import Fts5Retriever, RetrievedChunk, VectorRetriever
from rag.reranker    import reciprocal_rank_fusion


# ── Mock 工具 ─────────────────────────────────────────────────────────────────

class MockEmbeddingBackend(EmbeddingBackend):
    def __init__(self, dim: int = 4, should_raise: Exception | None = None) -> None:
        self._dim = dim
        self._should_raise = should_raise

    def is_available(self) -> bool:
        return True

    def encode(self, texts: list[str]) -> list[EmbeddingVector]:
        if self._should_raise:
            raise self._should_raise
        return [EmbeddingVector(text=t, vector=[0.1] * self._dim) for t in texts]

    @property
    def model_name(self) -> str:
        return "mock"

    @property
    def dimension(self) -> int:
        return self._dim


class MockLlmBackend(LlmBackend):
    def __init__(self, response: str = "模拟回答", available: bool = True) -> None:
        self._response  = response
        self._available = available
        self.call_count = 0
        self.last_prompt: str = ""

    def is_available(self) -> bool:
        return self._available

    def complete(self, prompt: str, system: str = "", **kwargs) -> LlmResponse:
        self.call_count += 1
        self.last_prompt = prompt
        return LlmResponse(text=self._response, model="mock-llm", tokens=10)

    @property
    def model_name(self) -> str:
        return "mock-llm"


class MockFts5Retriever:
    """鸭子类型 Fts5Retriever（无需 SQLite 连接）"""
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self._chunks    = chunks or []
        self.call_count = 0

    def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        self.call_count += 1
        return self._chunks[:top_k]


class MockVectorRetriever:
    """鸭子类型 VectorRetriever（无需 Qdrant 连接）"""
    def __init__(
        self,
        chunks:    list[RetrievedChunk] | None = None,
        available: bool = True,
    ) -> None:
        self._chunks    = chunks or []
        self._available = available
        self.call_count = 0

    def is_available(self) -> bool:
        return self._available

    def search(self, query_vector: list[float], top_k: int = 10) -> list[RetrievedChunk]:
        self.call_count += 1
        return self._chunks[:top_k]

    def upsert(self, *args, **kwargs) -> bool:
        return True


def _chunk(cid: int, score: float = 0.5, source: str = "fts5") -> RetrievedChunk:
    return RetrievedChunk(capture_id=cid, text=f"内容-{cid}", score=score, source=source)


def _make_pipeline(
    fts_chunks:    list[RetrievedChunk] | None = None,
    vector_chunks: list[RetrievedChunk] | None = None,
    llm_response:  str                         = "测试回答",
    embed_raise:   Exception | None            = None,
    top_k:         int                         = 3,
) -> RagPipeline:
    return RagPipeline(
        embedding_model  = EmbeddingModel(backend=MockEmbeddingBackend(should_raise=embed_raise)),
        vector_retriever = MockVectorRetriever(chunks=vector_chunks),  # type: ignore[arg-type]
        fts5_retriever   = MockFts5Retriever(chunks=fts_chunks),       # type: ignore[arg-type]
        llm              = MockLlmBackend(response=llm_response),
        top_k            = top_k,
    )


# ── RetrievedChunk ────────────────────────────────────────────────────────────

class TestRetrievedChunk:
    def test_basic_fields(self):
        chunk = RetrievedChunk(capture_id=1, text="工作记录", score=0.9, source="fts5")
        assert chunk.capture_id == 1
        assert chunk.text == "工作记录"
        assert chunk.score == pytest.approx(0.9)
        assert chunk.source == "fts5"

    def test_default_metadata(self):
        chunk = RetrievedChunk(capture_id=1, text="text")
        assert chunk.metadata == {}

    def test_default_score(self):
        chunk = RetrievedChunk(capture_id=1, text="text")
        assert chunk.score == 0.0

    def test_default_source(self):
        chunk = RetrievedChunk(capture_id=1, text="text")
        assert chunk.source == "unknown"


# ── RRF ──────────────────────────────────────────────────────────────────────

class TestRrf:
    def test_merges_two_lists(self):
        list1  = [_chunk(1, 0.9), _chunk(2, 0.8)]
        list2  = [_chunk(1, 0.7), _chunk(3, 0.6)]
        merged = reciprocal_rank_fusion([list1, list2], top_k=3)
        # chunk 1 出现在两个列表，RRF 分数最高
        assert merged[0].capture_id == 1

    def test_all_sources_marked_merged(self):
        list1  = [_chunk(1), _chunk(2)]
        merged = reciprocal_rank_fusion([list1])
        assert all(c.source == "merged" for c in merged)

    def test_empty_lists(self):
        assert reciprocal_rank_fusion([[], []]) == []

    def test_single_list(self):
        list1  = [_chunk(1), _chunk(2), _chunk(3)]
        merged = reciprocal_rank_fusion([list1], top_k=2)
        assert len(merged) == 2

    def test_top_k_respected(self):
        list1  = [_chunk(i) for i in range(10)]
        merged = reciprocal_rank_fusion([list1], top_k=4)
        assert len(merged) == 4

    def test_scores_positive(self):
        list1  = [_chunk(1), _chunk(2)]
        merged = reciprocal_rank_fusion([list1])
        assert all(c.score > 0 for c in merged)

    def test_deduplication(self):
        """同一 chunk 出现在两个列表时，合并后只有一条"""
        list1  = [_chunk(1)]
        list2  = [_chunk(1)]
        merged = reciprocal_rank_fusion([list1, list2])
        cids   = [c.capture_id for c in merged]
        assert len(cids) == len(set(cids))

    def test_ranking_by_appearance(self):
        """出现在更多列表的 chunk 排名应更高"""
        list1 = [_chunk(10), _chunk(20)]
        list2 = [_chunk(20), _chunk(30)]
        list3 = [_chunk(20), _chunk(10)]
        merged = reciprocal_rank_fusion([list1, list2, list3])
        # chunk 20 出现在 3 个列表，应为第一名
        assert merged[0].capture_id == 20

    def test_custom_k(self):
        """不同 k 值应影响分数但结果数量不变"""
        list1    = [_chunk(1), _chunk(2)]
        merged60 = reciprocal_rank_fusion([list1], k=60)
        merged10 = reciprocal_rank_fusion([list1], k=10)
        assert len(merged60) == len(merged10) == 2
        # k=10 时分母更小，分数更高
        assert merged10[0].score > merged60[0].score


# ── RagPipeline ───────────────────────────────────────────────────────────────

class TestRagPipeline:
    def test_query_returns_rag_result(self):
        pipeline = _make_pipeline(
            fts_chunks=[_chunk(1, 0.8)],
        )
        result = pipeline.query("飞书会议")
        assert isinstance(result, RagResult)

    def test_answer_from_llm(self):
        pipeline = _make_pipeline(llm_response="记忆面包回答")
        result   = pipeline.query("任何问题")
        assert result.answer == "记忆面包回答"

    def test_contexts_included(self):
        fts = [_chunk(1, 0.9), _chunk(2, 0.7)]
        pipeline = _make_pipeline(fts_chunks=fts)
        result   = pipeline.query("工作内容")
        assert len(result.contexts) >= 1

    def test_model_in_result(self):
        pipeline = _make_pipeline()
        result   = pipeline.query("问题")
        assert result.model == "mock-llm"

    def test_empty_context_still_answers(self):
        """无上下文时 LLM 仍然被调用"""
        pipeline = _make_pipeline(fts_chunks=[], vector_chunks=[])
        result   = pipeline.query("没有上下文的问题")
        assert result.answer is not None

    def test_llm_called_once(self):
        llm      = MockLlmBackend()
        pipeline = RagPipeline(
            embedding_model  = EmbeddingModel(backend=MockEmbeddingBackend()),
            vector_retriever = MockVectorRetriever(),  # type: ignore[arg-type]
            fts5_retriever   = MockFts5Retriever(),    # type: ignore[arg-type]
            llm              = llm,
        )
        pipeline.query("问题")
        assert llm.call_count == 1

    def test_top_k_limits_contexts(self):
        fts      = [_chunk(i, 0.9 - i * 0.05) for i in range(10)]
        pipeline = _make_pipeline(fts_chunks=fts, top_k=3)
        result   = pipeline.query("问题")
        assert len(result.contexts) <= 3

    def test_embedding_failure_degrades_gracefully(self):
        """embedding 失败应降级为纯 FTS5 检索，不抛异常"""
        fts      = [_chunk(1, 0.8)]
        pipeline = _make_pipeline(
            fts_chunks=fts,
            embed_raise=RuntimeError("embedding 服务不可用"),
        )
        result = pipeline.query("工作记录")
        # 应仍然返回 FTS5 结果
        assert result.answer is not None
        assert len(result.contexts) >= 1

    def test_prompt_contains_query(self):
        llm      = MockLlmBackend()
        pipeline = RagPipeline(
            embedding_model  = EmbeddingModel(backend=MockEmbeddingBackend()),
            vector_retriever = MockVectorRetriever(),  # type: ignore[arg-type]
            fts5_retriever   = MockFts5Retriever(),    # type: ignore[arg-type]
            llm              = llm,
        )
        pipeline.query("今日工作总结")
        assert "今日工作总结" in llm.last_prompt

    def test_vector_retriever_used_when_embedding_succeeds(self):
        vector_r = MockVectorRetriever(chunks=[_chunk(99)])
        pipeline = RagPipeline(
            embedding_model  = EmbeddingModel(backend=MockEmbeddingBackend()),
            vector_retriever = vector_r,               # type: ignore[arg-type]
            fts5_retriever   = MockFts5Retriever(),    # type: ignore[arg-type]
            llm              = MockLlmBackend(),
        )
        pipeline.query("问题")
        assert vector_r.call_count == 1

    def test_vector_retriever_skipped_when_embedding_fails(self):
        """embedding 失败时，向量检索应跳过"""
        vector_r = MockVectorRetriever()
        pipeline = RagPipeline(
            embedding_model  = EmbeddingModel(
                backend=MockEmbeddingBackend(should_raise=RuntimeError("embedding 失败"))
            ),
            vector_retriever = vector_r,               # type: ignore[arg-type]
            fts5_retriever   = MockFts5Retriever(),    # type: ignore[arg-type]
            llm              = MockLlmBackend(),
        )
        pipeline.query("问题")
        assert vector_r.call_count == 0


# ── VectorRetriever 接口测试 ──────────────────────────────────────────────────

class TestVectorRetriever:
    def test_is_available_returns_bool(self):
        retriever = VectorRetriever()
        assert isinstance(retriever.is_available(), bool)

    def test_search_returns_empty_when_unavailable(self):
        retriever = VectorRetriever()
        if not retriever.is_available():
            results = retriever.search([0.1, 0.2, 0.3], top_k=5)
            assert results == []

    def test_search_empty_vector_returns_empty(self):
        retriever = VectorRetriever()
        results   = retriever.search([], top_k=5)
        assert results == []

    def test_lazy_init(self):
        retriever = VectorRetriever()
        assert retriever._client is None


# ── OllamaBackend 接口测试 ────────────────────────────────────────────────────

class TestOllamaBackend:
    def test_model_name(self):
        backend = OllamaBackend(model="qwen2.5:7b")
        assert backend.model_name == "qwen2.5:7b"

    def test_is_available_returns_bool(self):
        backend = OllamaBackend()
        # Ollama 不一定运行，但不应抛异常
        assert isinstance(backend.is_available(), bool)

    def test_default_model(self):
        backend = OllamaBackend()
        assert "qwen" in backend.model_name.lower()
