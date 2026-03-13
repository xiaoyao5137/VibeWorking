"""
RRF (Reciprocal Rank Fusion) 多路结果合并器

将多路检索结果（FTS5、向量等）合并为统一排序列表，
消除不同打分量纲（BM25 vs 余弦相似度）的影响。

RRF 公式：score(d) = Σ [ 1 / (k + rank(d, list_i)) ]
常数 k=60（Cormack et al., 2009 推荐默认值）
"""

from __future__ import annotations

from .retriever import RetrievedChunk


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievedChunk]],
    top_k:        int = 10,
    k:            int = 60,
) -> list[RetrievedChunk]:
    """
    对多路检索结果执行 RRF 合并。

    Args:
        result_lists: 多路检索结果（每路已按相关性降序排列）
        top_k:        最终返回的 Top-K 结果数量
        k:            RRF 常数（默认 60）

    Returns:
        合并并重新排序的 RetrievedChunk 列表（source="merged"）
    """
    rrf_scores: dict[int, float]         = {}
    best_chunk: dict[int, RetrievedChunk] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results):
            cid = chunk.capture_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            # 保留原始分数最高的 chunk 作为内容代表
            if cid not in best_chunk or chunk.score > best_chunk[cid].score:
                best_chunk[cid] = chunk

    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

    return [
        RetrievedChunk(
            capture_id = cid,
            text       = best_chunk[cid].text,
            score      = rrf_scores[cid],
            source     = "merged",
            metadata   = best_chunk[cid].metadata,
        )
        for cid in sorted_ids
    ]
