#!/usr/bin/env python3
"""
手动测试知识提炼功能
模拟从 OCR 采集记录中提炼知识
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from knowledge.manager import KnowledgeManager
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    print("=" * 70)
    print("WorkBuddy 知识提炼功能手动测试")
    print("=" * 70)

    # 使用 WorkBuddy 数据库
    db_path = str(Path.home() / ".workbuddy" / "workbuddy.db")
    print(f"\n数据库路径: {db_path}")

    if not os.path.exists(db_path):
        print(f"⚠️  数据库不存在，将创建新数据库")

    manager = KnowledgeManager(db_path=db_path)
    print("✅ 知识库管理器初始化完成")

    # 模拟提炼的知识（因为 Ollama 未安装，使用预定义数据）
    print("\n" + "=" * 70)
    print("添加测试知识条目")
    print("=" * 70)

    test_knowledge = [
        {
            'capture_id': 1001,
            'summary': 'WorkBuddy 知识提炼功能开发完成，使用 Qwen3.5-4B 模型',
            'entities': json.dumps(['WorkBuddy', 'Qwen3.5', '知识提炼'], ensure_ascii=False),
            'category': '代码',
            'importance': 5,
        },
        {
            'capture_id': 1002,
            'summary': '测试知识库管理功能，包括添加、查询、更新、删除操作',
            'entities': json.dumps(['测试', '知识库', 'CRUD'], ensure_ascii=False),
            'category': '文档',
            'importance': 4,
        },
        {
            'capture_id': 1003,
            'summary': 'Desktop UI 新增知识库面板，用户可以查看和管理提炼的知识',
            'entities': json.dumps(['Desktop UI', '知识库面板', 'React'], ensure_ascii=False),
            'category': '代码',
            'importance': 4,
        },
    ]

    entry_ids = []
    for knowledge in test_knowledge:
        entry_id = manager.add_entry(knowledge)
        entry_ids.append(entry_id)
        print(f"✅ 添加知识条目 ID={entry_id}: {knowledge['summary'][:40]}...")

    # 查询知识库
    print("\n" + "=" * 70)
    print("查询知识库")
    print("=" * 70)

    entries = manager.get_entries(limit=10)
    print(f"\n共有 {len(entries)} 条知识:\n")

    for entry in entries:
        verified = "✅" if entry['user_verified'] else "❌"
        edited = "📝" if entry['user_edited'] else ""
        print(f"{verified} {edited} [{entry['id']}] {entry['category']:4s} {'⭐' * entry['importance']}")
        print(f"    {entry['summary']}")
        print(f"    实体: {', '.join(entry['entities'])}")
        print()

    # 分类统计
    print("=" * 70)
    print("分类统计")
    print("=" * 70)

    categories = ['会议', '文档', '代码', '聊天', '其他']
    for category in categories:
        count = manager.count_entries(category=category)
        if count > 0:
            print(f"✅ {category}: {count} 条")

    # 搜索测试
    print("\n" + "=" * 70)
    print("搜索测试")
    print("=" * 70)

    search_queries = ['WorkBuddy', 'Qwen', '知识库']
    for query in search_queries:
        results = manager.search_entries(query, limit=5)
        print(f"\n搜索 '{query}' 找到 {len(results)} 条结果:")
        for result in results:
            print(f"  - [{result['id']}] {result['summary'][:50]}...")

    print("\n" + "=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)
    print(f"\n现在可以在 Desktop UI 中查看知识库:")
    print("1. 打开 WorkBuddy 应用窗口")
    print("2. 点击悬浮按钮上的 📚 图标")
    print("3. 查看提炼的知识条目")
    print("\n或访问: http://localhost:1420/")

if __name__ == "__main__":
    main()
