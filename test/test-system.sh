#!/bin/bash

echo "╔════════════════════════════════════════════════════════════╗"
echo "║           WorkBuddy 系统测试                              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 测试 Core Engine
echo "🔧 测试 Core Engine..."
HEALTH=$(curl -s http://localhost:7070/health)
if echo "$HEALTH" | grep -q "ok"; then
    echo "✅ Core Engine: 运行正常"
    echo "   $HEALTH"
else
    echo "❌ Core Engine: 未运行或异常"
    exit 1
fi

echo ""

# 测试统计 API
echo "📊 测试统计 API..."
STATS=$(curl -s http://localhost:7070/api/stats)
echo "✅ 统计数据:"
echo "   $STATS"

echo ""

# 测试向量化状态
echo "🔍 测试向量化状态..."
VECTOR=$(curl -s http://localhost:7070/api/vector/status)
echo "✅ 向量化状态:"
echo "   $VECTOR"

echo ""

# 检查 UI 进程
echo "🖥️  检查 Desktop UI..."
if ps aux | grep -q "[w]orkbuddy-desktop"; then
    echo "✅ Desktop UI: 运行中"
    UI_PID=$(ps aux | grep "[w]orkbuddy-desktop" | awk '{print $2}')
    echo "   PID: $UI_PID"
else
    echo "❌ Desktop UI: 未运行"
fi

echo ""

# 检查 Vite 开发服务器
echo "⚡ 检查 Vite 服务器..."
if curl -s http://localhost:1420 > /dev/null; then
    echo "✅ Vite: 运行正常 (http://localhost:1420)"
else
    echo "❌ Vite: 未运行"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║           测试完成！                                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
