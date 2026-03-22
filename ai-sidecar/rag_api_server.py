#!/usr/bin/env python3
"""
RAG 查询 HTTP 服务
在端口 7071 上提供 RAG 查询 API
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# 懒加载 RAG pipeline
_rag_pipeline = None

def get_rag_pipeline():
    """懒加载 RAG pipeline"""
    global _rag_pipeline
    if _rag_pipeline is None:
        logger.info("初始化 RAG pipeline...")
        from embedding.model import EmbeddingModel
        from rag.retriever import VectorRetriever, Fts5Retriever, KnowledgeFts5Retriever
        from rag.llm.ollama import OllamaBackend
        from rag.pipeline import RagPipeline

        db_path = str(Path.home() / ".memory-bread" / "memory-bread.db")
        qdrant_path = str(Path.home() / ".qdrant")

        embedding_model = EmbeddingModel.create_default()
        # 使用本地 Qdrant 模式
        vector_retriever = VectorRetriever(
            collection="memory_bread_captures",
            qdrant_path=qdrant_path
        )
        fts5_retriever = Fts5Retriever(db_path=db_path)
        knowledge_retriever = KnowledgeFts5Retriever(db_path=db_path)
        llm = OllamaBackend(model="qwen2.5:3b")  # 使用 3b 模型

        _rag_pipeline = RagPipeline(
            embedding_model=embedding_model,
            vector_retriever=vector_retriever,
            fts5_retriever=fts5_retriever,
            knowledge_retriever=knowledge_retriever,
            llm=llm,
            top_k=5,
        )
        logger.info("RAG pipeline 初始化完成")
    return _rag_pipeline

@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({"status": "ok", "service": "rag"})

@app.route('/query', methods=['POST'])
def rag_query():
    """RAG 查询接口"""
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': '缺少 query 参数'}), 400

        query = data['query']
        top_k = data.get('top_k', 5)

        logger.info(f"收到 RAG 查询: {query}")

        # 执行 RAG 查询
        pipeline = get_rag_pipeline()
        result = pipeline.query(query)

        # 转换为 JSON 格式
        contexts = [
            {
                'capture_id': chunk.capture_id,
                'text': chunk.text,
                'score': chunk.score,
                'source': chunk.source,
            }
            for chunk in result.contexts
        ]

        response = {
            'answer': result.answer,
            'contexts': contexts,
            'model': result.model,
        }

        logger.info(f"RAG 查询完成，返回 {len(contexts)} 条上下文")
        return jsonify(response)

    except Exception as e:
        logger.error(f"RAG 查询失败: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("启动 RAG 查询服务")
    logger.info("监听地址: http://127.0.0.1:7071")

    # 预加载 RAG pipeline（避免首次查询超时）
    logger.info("预加载 RAG pipeline...")
    get_rag_pipeline()
    logger.info("RAG pipeline 预加载完成")

    app.run(host='127.0.0.1', port=7071, debug=False, threaded=True)
