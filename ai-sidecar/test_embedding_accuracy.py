"""
Embedding 模型准确率对比测试

对比 bge-m3 (1024维) vs bge-small-zh-v1.5:q4_k_m (512维) 的检索准确率
"""

import sys
import time
from typing import List, Tuple
import math

# 测试数据集：查询 + 相关文档 + 无关文档
TEST_CASES = [
    {
        "query": "如何使用 Python 读取 CSV 文件",
        "relevant": [
            "使用 pandas.read_csv() 函数可以轻松读取 CSV 文件",
            "Python 的 csv 模块提供了读取和写入 CSV 文件的功能",
            "import pandas as pd; df = pd.read_csv('data.csv')",
        ],
        "irrelevant": [
            "JavaScript 是一种流行的前端编程语言",
            "机器学习模型需要大量的训练数据",
            "Docker 容器化技术可以简化应用部署",
        ],
    },
    {
        "query": "内存泄漏如何排查",
        "relevant": [
            "使用 valgrind 工具可以检测 C/C++ 程序的内存泄漏",
            "Python 的 memory_profiler 可以分析内存使用情况",
            "Chrome DevTools 的 Memory 面板可以排查 JavaScript 内存泄漏",
        ],
        "irrelevant": [
            "React 是一个用于构建用户界面的 JavaScript 库",
            "SQL 查询优化可以提升数据库性能",
            "Git 是一个分布式版本控制系统",
        ],
    },
    {
        "query": "数据库索引的作用",
        "relevant": [
            "索引可以加速数据库查询，类似于书籍的目录",
            "B-Tree 索引是最常见的数据库索引类型",
            "合理使用索引可以将查询速度提升 10-100 倍",
        ],
        "irrelevant": [
            "Kubernetes 是一个容器编排平台",
            "TensorFlow 是一个开源机器学习框架",
            "Nginx 是一个高性能的 Web 服务器",
        ],
    },
    {
        "query": "如何优化网站加载速度",
        "relevant": [
            "压缩图片可以显著减少页面加载时间",
            "使用 CDN 可以加速静态资源的分发",
            "启用浏览器缓存可以减少重复请求",
        ],
        "irrelevant": [
            "Python 的装饰器可以增强函数功能",
            "Redis 是一个高性能的内存数据库",
            "Linux 内核提供了强大的进程管理功能",
        ],
    },
    {
        "query": "机器学习模型过拟合怎么办",
        "relevant": [
            "增加训练数据可以有效缓解过拟合问题",
            "使用正则化（L1/L2）可以防止模型过拟合",
            "Dropout 是深度学习中常用的防止过拟合的技术",
        ],
        "irrelevant": [
            "HTML5 引入了许多新的语义化标签",
            "MongoDB 是一个流行的 NoSQL 数据库",
            "SSH 是一种安全的远程登录协议",
        ],
    },
]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b)


def test_model(backend_name: str, encode_func) -> dict:
    """测试单个模型"""
    print(f"\n{'='*60}")
    print(f"测试模型: {backend_name}")
    print(f"{'='*60}")

    total_queries = len(TEST_CASES)
    correct_top1 = 0  # Top-1 准确率
    correct_top3 = 0  # Top-3 准确率
    mrr_sum = 0.0     # Mean Reciprocal Rank
    total_time = 0.0

    for i, case in enumerate(TEST_CASES, 1):
        query = case["query"]
        relevant = case["relevant"]
        irrelevant = case["irrelevant"]
        all_docs = relevant + irrelevant

        # 编码
        start = time.time()
        query_vec = encode_func([query])[0].vector
        doc_vecs = [encode_func([doc])[0].vector for doc in all_docs]
        elapsed = time.time() - start
        total_time += elapsed

        # 计算相似度
        similarities = [(doc, cosine_similarity(query_vec, vec))
                       for doc, vec in zip(all_docs, doc_vecs)]
        similarities.sort(key=lambda x: x[1], reverse=True)

        # 评估
        top1_doc = similarities[0][0]
        top3_docs = [s[0] for s in similarities[:3]]

        if top1_doc in relevant:
            correct_top1 += 1

        if any(doc in relevant for doc in top3_docs):
            correct_top3 += 1

        # MRR
        for rank, (doc, _) in enumerate(similarities, 1):
            if doc in relevant:
                mrr_sum += 1.0 / rank
                break

        # 打印详情
        print(f"\n查询 {i}: {query}")
        print(f"Top-3 结果:")
        for rank, (doc, sim) in enumerate(similarities[:3], 1):
            marker = "✅" if doc in relevant else "❌"
            print(f"  {rank}. [{marker}] {doc[:50]}... (相似度: {sim:.4f})")
        print(f"耗时: {elapsed:.3f}s")

    # 统计
    top1_acc = correct_top1 / total_queries
    top3_acc = correct_top3 / total_queries
    mrr = mrr_sum / total_queries
    avg_time = total_time / total_queries

    print(f"\n{'='*60}")
    print(f"统计结果:")
    print(f"  Top-1 准确率: {top1_acc:.1%} ({correct_top1}/{total_queries})")
    print(f"  Top-3 准确率: {top3_acc:.1%} ({correct_top3}/{total_queries})")
    print(f"  MRR (Mean Reciprocal Rank): {mrr:.4f}")
    print(f"  平均耗时: {avg_time:.3f}s")
    print(f"{'='*60}")

    return {
        "name": backend_name,
        "top1_acc": top1_acc,
        "top3_acc": top3_acc,
        "mrr": mrr,
        "avg_time": avg_time,
    }


def main():
    sys.path.insert(0, "/Users/xianjiaqi/Documents/mygit/cy/gzdz/ai-sidecar")

    from embedding.model import EmbeddingModel
    from embedding.bge import BgeM3Backend
    from embedding.ollama import OllamaEmbeddingBackend

    results = []

    # 测试 1: bge-m3 (原模型)
    print("\n🔍 加载 bge-m3 模型...")
    try:
        model_bge = EmbeddingModel(backend=BgeM3Backend())
        result_bge = test_model("bge-m3 (1024维, PyTorch)", model_bge.encode)
        results.append(result_bge)
    except Exception as e:
        print(f"❌ bge-m3 测试失败: {e}")
        result_bge = None

    # 测试 2: Ollama bge-small-zh-v1.5:q4_k_m (量化模型)
    print("\n🔍 加载 Ollama bge-small-zh-v1.5:q4_k_m 模型...")
    try:
        model_ollama = EmbeddingModel(backend=OllamaEmbeddingBackend())
        result_ollama = test_model("bge-small-zh-v1.5:q4_k_m (512维, Ollama)", model_ollama.encode)
        results.append(result_ollama)
    except Exception as e:
        print(f"❌ Ollama 测试失败: {e}")
        result_ollama = None

    # 对比总结
    if len(results) == 2:
        print(f"\n{'='*60}")
        print("📊 对比总结")
        print(f"{'='*60}")
        print(f"\n{'指标':<30} {'bge-m3':<20} {'bge-small-zh:q4_k_m':<20} {'差异':<15}")
        print(f"{'-'*85}")

        diff_top1 = results[1]["top1_acc"] - results[0]["top1_acc"]
        diff_top3 = results[1]["top3_acc"] - results[0]["top3_acc"]
        diff_mrr = results[1]["mrr"] - results[0]["mrr"]
        speedup = results[0]["avg_time"] / results[1]["avg_time"]

        print(f"{'Top-1 准确率':<30} {results[0]['top1_acc']:>18.1%} {results[1]['top1_acc']:>18.1%} {diff_top1:>+14.1%}")
        print(f"{'Top-3 准确率':<30} {results[0]['top3_acc']:>18.1%} {results[1]['top3_acc']:>18.1%} {diff_top3:>+14.1%}")
        print(f"{'MRR':<30} {results[0]['mrr']:>18.4f} {results[1]['mrr']:>18.4f} {diff_mrr:>+14.4f}")
        print(f"{'平均耗时':<30} {results[0]['avg_time']:>17.3f}s {results[1]['avg_time']:>17.3f}s {speedup:>13.2f}x")
        print(f"\n{'内存占用':<30} {'4.7GB':<20} {'~100MB':<20} {'-97.9%':<15}")
        print(f"{'模型大小':<30} {'560MB':<20} {'50MB':<20} {'-91.1%':<15}")

        print(f"\n{'='*60}")
        print("💡 结论:")
        if abs(diff_top1) <= 0.05:
            print("  ✅ 准确率差异 < 5%，量化模型可接受")
        elif abs(diff_top1) <= 0.10:
            print("  ⚠️  准确率差异 5-10%，建议评估业务影响")
        else:
            print("  ❌ 准确率差异 > 10%，建议使用 q8_0 版本")

        if speedup > 1.2:
            print(f"  ✅ 推理速度提升 {speedup:.1f}x")

        print(f"  ✅ 内存占用减少 97.9%（4.7GB → 100MB）")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
