#!/bin/bash
# 记忆面包 RAG 功能测试脚本

RAG_URL="http://127.0.0.1:7071"

echo "============================================================"
echo "记忆面包 RAG 功能测试"
echo "============================================================"

# 测试健康检查
echo ""
echo "✅ 检查 RAG 服务状态..."
curl -s "$RAG_URL/health" | python3 -m json.tool
echo ""

# 测试问题列表
questions=(
    "我最近在用什么软件？"
    "我在看什么文档？"
    "我今天做了什么工作？"
)

# 执行测试
for i in "${!questions[@]}"; do
    question="${questions[$i]}"
    echo ""
    echo "============================================================"
    echo "测试 $((i+1)): $question"
    echo "============================================================"

    response=$(curl -s -X POST "$RAG_URL/query" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$question\", \"top_k\": 3}")

    # 解析并显示结果
    echo ""
    echo "💡 答案:"
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['answer'])"

    echo ""
    echo "📚 上下文数量:"
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data['contexts']), '条相关记录')"

    echo ""
    echo "🤖 使用模型:"
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['model'])"

    echo ""
done

echo "============================================================"
echo "测试完成！"
echo "============================================================"
