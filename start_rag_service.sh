#!/bin/bash
# 启动 RAG 查询服务

cd "$(dirname "$0")/ai-sidecar"

# 激活虚拟环境
source .venv/bin/activate

# 启动 RAG API 服务器
echo "启动 RAG 查询服务 (端口 7071)..."
python3 rag_api_server.py
