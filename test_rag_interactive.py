#!/usr/bin/env python3
"""
WorkBuddy RAG 交互式测试脚本
"""
import requests
import json
import sys

RAG_API_URL = "http://127.0.0.1:7071"

def test_health():
    """测试服务健康状态"""
    try:
        resp = requests.get(f"{RAG_API_URL}/health", timeout=5)
        if resp.status_code == 200:
            print("✅ RAG 服务运行正常")
            return True
        else:
            print(f"❌ RAG 服务异常: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到 RAG 服务: {e}")
        return False

def query_rag(question, top_k=5):
    """查询 RAG"""
    try:
        print(f"\n🔍 查询: {question}")
        print("-" * 60)

        resp = requests.post(
            f"{RAG_API_URL}/query",
            json={"query": question, "top_k": top_k},
            timeout=30
        )

        if resp.status_code != 200:
            print(f"❌ 查询失败: {resp.status_code}")
            print(resp.text)
            return None

        result = resp.json()

        # 显示答案
        print(f"\n💡 答案:")
        print(result['answer'])

        # 显示上下文
        contexts = result.get('contexts', [])
        print(f"\n📚 找到 {len(contexts)} 条相关记录:")
        for i, ctx in enumerate(contexts[:3], 1):  # 只显示前3条
            print(f"\n[{i}] (ID: {ctx['capture_id']}, 来源: {ctx['source']}, 分数: {ctx['score']:.4f})")
            text = ctx['text'][:150] + "..." if len(ctx['text']) > 150 else ctx['text']
            print(f"    {text}")

        print(f"\n🤖 模型: {result.get('model', 'unknown')}")
        print("-" * 60)

        return result

    except Exception as e:
        print(f"❌ 查询异常: {e}")
        return None

def main():
    print("=" * 60)
    print("WorkBuddy RAG 功能测试")
    print("=" * 60)

    # 检查服务
    if not test_health():
        sys.exit(1)

    # 预设测试问题
    test_questions = [
        "我最近在用什么软件？",
        "我在看什么文档？",
        "我今天做了什么工作？",
        "最近有什么重要的事情？",
    ]

    print("\n📋 预设测试问题:")
    for i, q in enumerate(test_questions, 1):
        print(f"  {i}. {q}")

    print("\n" + "=" * 60)

    # 交互式查询
    while True:
        print("\n请输入问题（输入数字选择预设问题，输入 'q' 退出）:")
        user_input = input("> ").strip()

        if user_input.lower() == 'q':
            print("\n👋 再见！")
            break

        # 检查是否是数字选择
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(test_questions):
                question = test_questions[idx]
            else:
                print("❌ 无效的选项")
                continue
        else:
            question = user_input

        if not question:
            continue

        # 执行查询
        query_rag(question)

if __name__ == "__main__":
    main()
