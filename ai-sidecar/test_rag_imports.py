"""测试 RAG 模块导入"""

import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """测试所有 RAG 相关模块是否可以导入"""
    
    tests = [
        ("embedding.vector_storage", "VectorStorage"),
        ("rag.worker", "RagWorker"),
        ("rag.retriever", "VectorRetriever"),
        ("rag.retriever", "Fts5Retriever"),
        ("rag.retriever", "KnowledgeFts5Retriever"),
        ("rag.retriever", "RetrievedChunk"),
        ("rag.pipeline", "RagPipeline"),
    ]
    
    passed = 0
    failed = 0
    
    for module_name, class_name in tests:
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls = getattr(module, class_name)
            logger.info(f"✅ {module_name}.{class_name}")
            passed += 1
        except Exception as e:
            logger.error(f"❌ {module_name}.{class_name}: {e}")
            failed += 1
    
    logger.info(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
