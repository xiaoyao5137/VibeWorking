#!/usr/bin/env python3
"""
测试知识提炼功能
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from knowledge.extractor import KnowledgeExtractor
from knowledge.manager import KnowledgeManager
import json
import logging

logging.basicConfig(level=logging.INFO)

def test_extraction():
    """测试知识提炼"""
    print("=" * 60)
    print("测试知识提炼功能")
    print("=" * 60)

    # 测试数据
    test_captures = [
        {
            'id': 1,
            'app_name': '飞书',
            'window_title': '产品评审会',
            'timestamp': '2026-03-07 10:30:00',
            'ocr_text': '''
            【飞书会议】产品评审会
            时间：2026-03-07 14:00
            参与人：张三、李四、王五

            讨论内容：
            1. Q1 产品路线图确认
            2. AI 功能优先级排序
            3. 下周开始开发

            决策：优先实现 OCR 采集功能
            '''
        },
        {
            'id': 2,
            'app_name': 'VSCode',
            'window_title': 'extractor.py',
            'timestamp': '2026-03-07 11:00:00',
            'ocr_text': '''
            class KnowledgeExtractor:
                def __init__(self):
                    self.client = Client()
                    self.model = "qwen3.5:4b"

                async def extract(self, capture_data):
                    # 提炼知识
                    pass
            '''
        },
        {
            'id': 3,
            'app_name': 'Chrome',
            'window_title': '新标签页',
            'timestamp': '2026-03-07 11:30:00',
            'ocr_text': '''
            Google
            [搜索框]
            [我很幸运]
            '''
        }
    ]

    extractor = KnowledgeExtractor()
    manager = KnowledgeManager()

    for capture in test_captures:
        print(f"\n处理采集记录 {capture['id']}: {capture['app_name']} - {capture['window_title']}")
        print("-" * 60)

        # 提炼知识
        knowledge = extractor.extract_sync(capture)

        if knowledge:
            print("✅ 提炼成功:")
            print(json.dumps(knowledge, indent=2, ensure_ascii=False))

            # 保存到数据库
            entry_id = manager.add_entry(knowledge)
            print(f"✅ 已保存到数据库，ID: {entry_id}")
        else:
            print("⏭️  无价值内容，已跳过")

    # 查询知识库
    print("\n" + "=" * 60)
    print("查询知识库")
    print("=" * 60)

    entries = manager.get_entries(limit=10)
    print(f"\n共有 {len(entries)} 条知识:")

    for entry in entries:
        print(f"\n[{entry['id']}] {entry['category']} - 重要性: {'⭐' * entry['importance']}")
        print(f"摘要: {entry['summary']}")
        print(f"实体: {', '.join(entry['entities'])}")
        print(f"验证: {'✅' if entry['user_verified'] else '❌'}")

    # 测试搜索
    print("\n" + "=" * 60)
    print("测试搜索功能")
    print("=" * 60)

    search_query = "产品"
    results = manager.search_entries(search_query, limit=5)
    print(f"\n搜索 '{search_query}' 找到 {len(results)} 条结果:")

    for result in results:
        print(f"- [{result['id']}] {result['summary'][:50]}...")

if __name__ == "__main__":
    test_extraction()
