#!/usr/bin/env python3
"""
测试知识库管理功能（不依赖 Ollama）
使用模拟数据测试数据库操作
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from knowledge.manager import KnowledgeManager
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_knowledge_manager():
    """测试知识库管理器"""
    print("=" * 70)
    print("测试知识库管理功能（不依赖 Ollama）")
    print("=" * 70)

    # 使用临时数据库
    test_db = "/tmp/test_workbuddy.db"
    if os.path.exists(test_db):
        os.remove(test_db)
        print(f"✅ 清理旧测试数据库")

    manager = KnowledgeManager(db_path=test_db)
    print(f"✅ 初始化知识库管理器: {test_db}")

    # 模拟提炼后的知识数据
    mock_knowledge_entries = [
        {
            'capture_id': 1,
            'summary': '产品评审会确定 Q1 路线图，优先开发 OCR 采集功能',
            'entities': json.dumps(['张三', '李四', '王五', 'Q1', 'OCR'], ensure_ascii=False),
            'category': '会议',
            'importance': 5,
        },
        {
            'capture_id': 2,
            'summary': '编写了 PaddleOCR 的 Python 封装代码，实现了图像预处理和文本识别',
            'entities': json.dumps(['PaddleOCR', 'Python', 'FastAPI'], ensure_ascii=False),
            'category': '代码',
            'importance': 4,
        },
        {
            'capture_id': 3,
            'summary': '与客户讨论项目需求，确认了交付时间和功能范围',
            'entities': json.dumps(['客户', '项目需求', '交付时间'], ensure_ascii=False),
            'category': '会议',
            'importance': 4,
        },
        {
            'capture_id': 4,
            'summary': '阅读了 Qwen3.5 技术文档，了解了模型架构和 API 使用方法',
            'entities': json.dumps(['Qwen3.5', 'API', '技术文档'], ensure_ascii=False),
            'category': '文档',
            'importance': 3,
        },
        {
            'capture_id': 5,
            'summary': '在飞书群里讨论了周末团建活动的安排',
            'entities': json.dumps(['飞书', '团建', '周末'], ensure_ascii=False),
            'category': '聊天',
            'importance': 2,
        },
    ]

    # 1. 测试添加知识条目
    print("\n" + "=" * 70)
    print("1. 测试添加知识条目")
    print("=" * 70)

    entry_ids = []
    for i, knowledge in enumerate(mock_knowledge_entries, 1):
        entry_id = manager.add_entry(knowledge)
        entry_ids.append(entry_id)
        print(f"✅ [{i}] 添加知识条目 ID={entry_id}: {knowledge['summary'][:40]}...")

    # 2. 测试获取知识列表
    print("\n" + "=" * 70)
    print("2. 测试获取知识列表")
    print("=" * 70)

    entries = manager.get_entries(limit=10)
    print(f"\n共有 {len(entries)} 条知识:\n")

    for entry in entries:
        print(f"[{entry['id']}] {entry['category']} - {'⭐' * entry['importance']}")
        print(f"    摘要: {entry['summary']}")
        print(f"    实体: {', '.join(entry['entities'])}")
        print(f"    验证: {'✅' if entry['user_verified'] else '❌'}")
        print()

    # 3. 测试分类筛选
    print("=" * 70)
    print("3. 测试分类筛选")
    print("=" * 70)

    categories = ['会议', '代码', '文档', '聊天']
    for category in categories:
        filtered = manager.get_entries(category=category, limit=10)
        print(f"✅ {category}: {len(filtered)} 条")

    # 4. 测试搜索功能
    print("\n" + "=" * 70)
    print("4. 测试搜索功能")
    print("=" * 70)

    search_queries = ['产品', 'OCR', 'Python', '会议']
    for query in search_queries:
        results = manager.search_entries(query, limit=5)
        print(f"\n搜索 '{query}' 找到 {len(results)} 条结果:")
        for result in results:
            print(f"  - [{result['id']}] {result['summary'][:50]}...")

    # 5. 测试更新知识条目
    print("\n" + "=" * 70)
    print("5. 测试更新知识条目")
    print("=" * 70)

    if entry_ids:
        test_id = entry_ids[0]
        updates = {
            'summary': '【已更新】产品评审会确定 Q1 路线图，优先开发 OCR 采集功能',
            'importance': 5,
            'user_edited': True
        }
        success = manager.update_entry(test_id, updates)
        if success:
            print(f"✅ 更新知识条目 {test_id} 成功")
            updated = manager.get_entry(test_id)
            print(f"    新摘要: {updated['summary']}")
        else:
            print(f"❌ 更新失败")

    # 6. 测试验证知识条目
    print("\n" + "=" * 70)
    print("6. 测试验证知识条目")
    print("=" * 70)

    if entry_ids:
        test_id = entry_ids[1]
        success = manager.update_entry(test_id, {'user_verified': True})
        if success:
            print(f"✅ 验证知识条目 {test_id} 成功")
            verified = manager.get_entry(test_id)
            print(f"    验证状态: {'✅' if verified['user_verified'] else '❌'}")

    # 7. 测试统计功能
    print("\n" + "=" * 70)
    print("7. 测试统计功能")
    print("=" * 70)

    total = manager.count_entries()
    verified_count = manager.count_entries(verified_only=True)
    print(f"✅ 总条目数: {total}")
    print(f"✅ 已验证条目数: {verified_count}")

    for category in categories:
        count = manager.count_entries(category=category)
        print(f"✅ {category} 类别: {count} 条")

    # 8. 测试删除知识条目
    print("\n" + "=" * 70)
    print("8. 测试删除知识条目")
    print("=" * 70)

    if entry_ids:
        test_id = entry_ids[-1]
        entry = manager.get_entry(test_id)
        print(f"准备删除: [{test_id}] {entry['summary'][:40]}...")

        success = manager.delete_entry(test_id)
        if success:
            print(f"✅ 删除知识条目 {test_id} 成功")
            remaining = manager.count_entries()
            print(f"✅ 剩余条目数: {remaining}")
        else:
            print(f"❌ 删除失败")

    # 9. 最终统计
    print("\n" + "=" * 70)
    print("9. 最终统计")
    print("=" * 70)

    final_entries = manager.get_entries(limit=100)
    print(f"\n最终知识库包含 {len(final_entries)} 条知识:\n")

    for entry in final_entries:
        status = "✅" if entry['user_verified'] else "❌"
        edited = "📝" if entry['user_edited'] else ""
        print(f"{status} {edited} [{entry['id']}] {entry['category']:4s} {'⭐' * entry['importance']} {entry['summary'][:50]}...")

    print("\n" + "=" * 70)
    print("✅ 所有测试完成！")
    print("=" * 70)
    print(f"\n测试数据库位置: {test_db}")
    print("可以使用 sqlite3 命令查看:")
    print(f"  sqlite3 {test_db}")
    print(f"  SELECT * FROM knowledge_entries;")

if __name__ == "__main__":
    try:
        test_knowledge_manager()
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        sys.exit(1)
