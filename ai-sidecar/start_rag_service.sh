#!/bin/bash
# 启动 RAG HTTP 服务（端口 7071）

cd "$(dirname "$0")"
source .venv/bin/activate

echo "🚀 启动 RAG HTTP 服务..."
echo "📍 监听地址: http://127.0.0.1:7071"
echo ""

# 使用现有的 rag_api_server.py
python rag_api_server.py
