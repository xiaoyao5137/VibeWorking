"""
知识提炼模块 V2 - 强制使用 LLM，支持去重和出现次数统计
"""

import json
import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个专业的工作记录提炼助手。你的任务是从 OCR 识别的屏幕文本中提取有价值的工作信息。

**提炼规则**：
1. 忽略 UI 元素（按钮、菜单、状态栏等）
2. 提取核心工作内容（会议记录、文档内容、代码片段、聊天记录等）
3. 生成"概述"和"明细"两部分内容：
   - 概述：简洁描述在做什么事情（30-100字），使用过去时态，避免使用"正在"等词
   - 明细：详细记录具体内容细节，保留关键信息以便后期追溯（200-500字）
4. 识别关键实体（人名、项目名、时间、地点）
5. 如果内容无价值（纯 UI、重复内容），返回 "SKIP"

**输出格式**（JSON）：
{
  "overview": "概述文本，描述做了什么事情，不要包含换行符",
  "details": "明细文本，使用空格代替换行符",
  "entities": ["实体1", "实体2"],
  "category": "会议|文档|代码|聊天|其他",
  "importance": 1-5
}

**重要性评分标准**：
- 5分：关键决策、重要会议纪要、核心代码逻辑
- 4分：项目进展、技术文档、重要沟通
- 3分：日常工作记录、一般文档
- 2分：简单操作记录
- 1分：无关紧要的内容

**明细内容要求**：
- 保留足够的上下文信息
- 记录关键对话内容和参与人
- 保留代码片段和技术细节
- 记录决策过程和理由
- 便于后期回忆和追溯
- 所有文本必须在一行内，不要使用换行符

**注意**：输出必须是有效的 JSON 格式，字符串中的引号要转义，不要包含未转义的换行符。
"""


class KnowledgeExtractorV2:
    """知识提炼器 V2 - 强制使用 LLM"""

    def __init__(self, model: str = "qwen2.5:3b", embedding_model=None):
        """
        初始化知识提炼器

        Args:
            model: Ollama 模型名称
            embedding_model: 向量模型（用于去重）
        """
        try:
            from ollama import Client
            self.client = Client()
            self.model = model

            # 测试模型是否可用
            try:
                self.client.list()
                logger.info(f"✅ Ollama 客户端初始化成功，模型: {model}")
            except Exception as e:
                raise RuntimeError(f"Ollama 服务不可用: {e}")

        except ImportError:
            raise RuntimeError("Ollama 未安装，请先安装: pip install ollama")

        self.embedding_model = embedding_model
        if embedding_model:
            logger.info("✅ 向量模型已加载，将启用知识去重")

    def _build_prompt(self, capture_data: Dict[str, Any]) -> str:
        """构建提炼 prompt"""
        app_name = capture_data.get('app_name', '未知应用')
        window_title = capture_data.get('window_title', '未知窗口')
        timestamp = capture_data.get('timestamp', datetime.now().isoformat())
        ocr_text = capture_data.get('ocr_text', '')

        # 限制文本长度，避免超过上下文
        if len(ocr_text) > 2000:
            ocr_text = ocr_text[:2000] + "..."

        prompt = f"""**应用名称**：{app_name}
**窗口标题**：{window_title}
**时间戳**：{timestamp}
**OCR 文本**：
{ocr_text}

请提炼上述内容。"""

        return prompt

    def _find_similar_knowledge(
        self,
        overview: str,
        db_conn,
        threshold: float = 0.85
    ) -> Optional[int]:
        """
        查找相似的知识条目

        Args:
            overview: 新的概述
            db_conn: 数据库连接
            threshold: 相似度阈值（0-1）

        Returns:
            相似知识条目的 ID，如果没有则返回 None
        """
        if not self.embedding_model:
            return None

        try:
            # 1. 获取新概述的向量
            new_embedding = self.embedding_model.encode([overview])[0]
            new_vector = np.array(new_embedding.vector)

            # 2. 获取所有现有知识条目
            cursor = db_conn.execute(
                "SELECT id, overview FROM knowledge_entries WHERE overview IS NOT NULL ORDER BY created_at DESC LIMIT 1000"
            )
            existing_entries = cursor.fetchall()

            if not existing_entries:
                return None

            # 3. 计算相似度
            for entry_id, existing_overview in existing_entries:
                if not existing_overview:
                    continue

                existing_embedding = self.embedding_model.encode([existing_overview])[0]
                existing_vector = np.array(existing_embedding.vector)

                # 余弦相似度
                similarity = np.dot(new_vector, existing_vector) / (
                    np.linalg.norm(new_vector) * np.linalg.norm(existing_vector)
                )

                if similarity >= threshold:
                    logger.info(f"发现相似知识条目 (ID={entry_id}, 相似度={similarity:.2f})")
                    return entry_id

            return None

        except Exception as e:
            logger.error(f"查找相似知识失败: {e}")
            return None

    def extract_sync(
        self,
        capture_data: Dict[str, Any],
        db_conn=None
    ) -> Optional[Dict[str, Any]]:
        """
        同步版本的提炼方法

        Args:
            capture_data: 采集数据
            db_conn: 数据库连接（用于去重）

        Returns:
            提炼后的知识，如果无价值或重复则返回 None
        """
        try:
            # 1. 构建 prompt
            prompt = self._build_prompt(capture_data)

            # 2. 调用本地 LLM
            logger.info(f"开始提炼采集记录 {capture_data.get('id')}")
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                format="json",
                options={
                    "temperature": 0.3,
                    "num_predict": 1024,  # 增加到 1024 tokens 以支持详细内容
                }
            )

            # 3. 解析结果
            content = response['message']['content']
            result = json.loads(content)

            # 4. 跳过无价值内容
            overview = result.get('overview', '')
            if overview == 'SKIP' or not overview:
                logger.info(f"采集记录 {capture_data.get('id')} 无价值，跳过")
                return None

            details = result.get('details', '')

            # 5. 去重检查和知识合并
            if db_conn:
                similar_id = self._find_similar_knowledge(overview, db_conn)
                if similar_id:
                    # 合并知识：更新明细内容，追加新的细节
                    cursor = db_conn.execute(
                        "SELECT details FROM knowledge_entries WHERE id = ?",
                        (similar_id,)
                    )
                    existing_details = cursor.fetchone()[0] or ""

                    # 合并明细：保留原有内容，追加新内容
                    merged_details = existing_details
                    if details and details not in existing_details:
                        merged_details += f"\n\n--- 补充 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ---\n{details}"

                    # 更新现有记录
                    db_conn.execute(
                        """UPDATE knowledge_entries
                           SET occurrence_count = occurrence_count + 1,
                               details = ?,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (merged_details, similar_id)
                    )
                    db_conn.commit()
                    logger.info(f"知识已合并到现有条目 (ID={similar_id})")
                    return None

            # 6. 返回结构化知识
            knowledge = {
                'capture_id': capture_data['id'],
                'overview': overview,
                'details': details,
                'entities': json.dumps(result.get('entities', []), ensure_ascii=False),
                'category': result.get('category', '其他'),
                'importance': result.get('importance', 3),
                'occurrence_count': 1,
            }

            logger.info(f"成功提炼采集记录 {capture_data.get('id')}: {overview[:50]}...")
            return knowledge

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"知识提炼失败: {e}")
            return None

    async def extract(
        self,
        capture_data: Dict[str, Any],
        db_conn=None
    ) -> Optional[Dict[str, Any]]:
        """异步版本（调用同步方法）"""
        return self.extract_sync(capture_data, db_conn)
