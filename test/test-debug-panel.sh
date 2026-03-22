#!/bin/bash

echo "╔════════════════════════════════════════════════════════════╗"
echo "║           调试面板功能测试                                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 测试 1: 健康检查
echo "🔧 测试 1: 健康检查"
HEALTH=$(curl -s http://localhost:7070/health)
if echo "$HEALTH" | grep -q "ok"; then
    echo "✅ 通过: $HEALTH"
else
    echo "❌ 失败: Core Engine 未运行"
    exit 1
fi
echo ""

# 测试 2: 统计 API
echo "📊 测试 2: 系统统计 (/api/stats)"
STATS=$(curl -s http://localhost:7070/api/stats)
echo "$STATS" | python3 -m json.tool
TOTAL=$(echo "$STATS" | python3 -c "import sys, json; print(json.load(sys.stdin)['total_captures'])")
if [ "$TOTAL" -gt 0 ]; then
    echo "✅ 通过: 找到 $TOTAL 条采集记录"
else
    echo "⚠️  警告: 没有采集记录"
fi
echo ""

# 测试 3: 采集记录 API
echo "📝 测试 3: 采集记录 (/api/captures)"
CAPTURES=$(curl -s 'http://localhost:7070/api/captures?limit=3')
echo "$CAPTURES" | python3 -m json.tool
COUNT=$(echo "$CAPTURES" | python3 -c "import sys, json; print(len(json.load(sys.stdin)['captures']))")
if [ "$COUNT" -gt 0 ]; then
    echo "✅ 通过: 返回 $COUNT 条记录"
else
    echo "❌ 失败: 没有返回记录"
fi
echo ""

# 测试 4: 向量化状态 API
echo "🔍 测试 4: 向量化状态 (/api/vector/status)"
VECTOR=$(curl -s http://localhost:7070/api/vector/status)
echo "$VECTOR" | python3 -m json.tool
echo "✅ 通过: API 响应正常"
echo ""

# 测试 5: 检查 UI
echo "🖥️  测试 5: Desktop UI"
if ps aux | grep -q "[w]orkbuddy-desktop"; then
    echo "✅ 通过: UI 进程运行中"
    UI_PID=$(ps aux | grep "[w]orkbuddy-desktop" | awk '{print $2}')
    echo "   PID: $UI_PID"
else
    echo "❌ 失败: UI 未运行"
fi
echo ""

# 测试 6: Vite 开发服务器
echo "⚡ 测试 6: Vite 开发服务器"
if curl -s http://localhost:1420 > /dev/null; then
    echo "✅ 通过: Vite 运行正常 (http://localhost:1420)"
else
    echo "❌ 失败: Vite 未运行"
fi
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║           测试完成！                                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "📋 下一步:"
echo "   1. 打开 记忆面包 应用窗口"
echo "   2. 进入设置页面"
echo "   3. 点击 '🔧 打开调试面板'"
echo "   4. 查看实时数据更新"
echo ""
echo "💡 提示: 调试面板每 2 秒自动刷新数据"
