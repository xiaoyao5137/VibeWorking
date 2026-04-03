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


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """尽量从 LLM 输出中提取第一个合法 JSON 对象。"""
    if not raw:
        return None

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                candidate = text[start:idx + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None

    return None


MERGE_SYSTEM_PROMPT ="""你是一个工作片段提炼助手。以下是用户在一段连续时间内的屏幕采集记录（按时间顺序），它们属于同一个工作片段。

**你的任务**：将这些连续采集提炼为一个完整的工作片段知识条目。

**提炼规则**：
1. 识别这段时间内用户在做的一件完整的事
2. 生成概述（50-150字）：描述做了什么、关键进展、结果，使用过去时态
3. 生成明细（200-500字）：
   - 保留有追溯价值的具体信息（代码逻辑、会议决策、学到的知识点）
   - 过滤掉 UI 操作、重复内容、无意义的切换记录
   - 不要堆砌原始文本，要提炼和归纳
4. 识别关键实体（人名、项目名、技术词汇）
5. 判断分类和重要性

**输出格式（JSON）**：
{
  "overview": "概述，50-150字，不含换行符",
  "details": "明细，200-500字，使用空格代替换行符",
  "entities": ["实体1", "实体2"],
  "category": "会议|文档|代码|聊天|学习|其他",
  "importance": 1-5,
  "history_view": true,
  "content_origin": "live_interaction|historical_content|document_reference|other",
  "activity_type": "meeting|coding|reading|chat|ask_ai|reviewing_history|other",
  "event_time_start": 1710000000000,
  "event_time_end": 1710003600000,
  "evidence_strength": "low|medium|high"
}

**注意补充判断**：
- 如果用户今天在 IM/聊天/AI 工具里回看昨天、前天、更早的消息或历史对话，`history_view=true`
- `observed_at` 不需要输出，由系统记录当前片段结束时间
- `event_time_start/event_time_end` 只在内容明确提到事情发生时间时填写；不明确时返回 null
- 询问 Gemini/Claude/ChatGPT 等 AI 助手，通常可标为 `activity_type=ask_ai`
- 查看历史消息/历史会话，通常可标为 `activity_type=reviewing_history` 且 `content_origin=historical_content`
- 直接实时聊天或会议记录，通常 `content_origin=live_interaction`
- 证据弱、推断成分高时降低 `evidence_strength`

**重要性评分**：
- 5分：关键决策、重要会议纪要、核心代码逻辑
- 4分：项目进展、技术文档、重要沟通
- 3分：日常工作记录、一般文档
- 2分：简单操作记录
- 1分：无关紧要的内容

**注意**：输出必须是有效的 JSON，字符串中的引号要转义，不要包含未转义的换行符。
"""

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


def _build_fallback_knowledge(captures: List[Dict[str, Any]], reason: str) -> Optional[Dict[str, Any]]:
    """当 LLM 输出异常时，生成兜底 knowledge，避免队头 capture 永久卡住。"""
    if not captures:
        return None

    text_samples = []
    for capture in captures:
        text = (capture.get('ocr_text') or capture.get('ax_text') or '').strip()
        if text:
            text_samples.append(text.replace('\n', ' ')[:200])

    if not text_samples:
        return None

    start_time = captures[0]['ts']
    end_time = captures[-1]['ts']
    duration_minutes = max(0, int((end_time - start_time) / 60000))

    from collections import Counter
    app_counter = Counter(c.get('app_name') for c in captures if c.get('app_name'))
    frag_app_name = app_counter.most_common(1)[0][0] if app_counter else None
    frag_win_title = next(
        (c.get('window_title') for c in reversed(captures) if c.get('window_title')),
        None,
    )

    details = ' '.join(text_samples[:5])
    if len(details) > 500:
        details = details[:500]

    return {
        'capture_ids': json.dumps([c['id'] for c in captures]),
        'overview': f'低价值工作片段（{reason}）',
        'details': details,
        'entities': json.dumps([], ensure_ascii=False),
        'category': '其他',
        'importance': 1,
        'occurrence_count': 1,
        'start_time': start_time,
        'end_time': end_time,
        'duration_minutes': duration_minutes,
        'frag_app_name': frag_app_name,
        'frag_win_title': frag_win_title,
        'observed_at': end_time,
        'event_time_start': None,
        'event_time_end': None,
        'history_view': False,
        'content_origin': 'other',
        'activity_type': 'other',
        'is_self_generated': False,
        'evidence_strength': 'low',
    }


class KnowledgeExtractorV2:
    """知识提炼器 V2 - 强制使用 LLM"""

    def __init__(self, model: str = "qwen2.5:3b", embedding_model=None, user_identity: str = ""):
        """
        初始化知识提炼器

        Args:
            model: Ollama 模型名称
            embedding_model: 向量模型（用于去重）
            user_identity: 用户身份关键词，多个用逗号分隔（如 "张三,zhangsan"）
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

        self.user_identity = user_identity.strip()
        if self.user_identity:
            logger.info(f"✅ 用户身份已配置: {self.user_identity}")

    def _build_merge_system_prompt(self) -> str:
        """构建带用户身份的 MERGE_SYSTEM_PROMPT"""
        identity_clause = ""
        if self.user_identity:
            names = [n.strip() for n in self.user_identity.split(",") if n.strip()]
            names_str = "、".join(f'"{n}"' for n in names)
            identity_clause = (
                f"\n\n**用户身份信息**：屏幕的使用者是 {names_str}。"
                "在提炼时，请注意：\n"
                "- 如果屏幕内容是该用户自己操作、输入、编写的工作，activity_type 应正确标注为对应类型（coding/reading/chat 等）\n"
                "- 如果屏幕内容显示的是其他人（非该用户）的工作、他人的对话记录、别人的代码或文档，overview 中应明确说明「用户在查看他人的…」，importance 降低 1-2 分\n"
                "- 如果无法判断内容主体，按正常流程提炼，不要猜测"
            )
        return MERGE_SYSTEM_PROMPT + identity_clause

    def _build_prompt(self, capture_data: Dict[str, Any]) -> str:
        """构建提炼 prompt"""
        app_name = capture_data.get('app_name', '未知应用')
        window_title = capture_data.get('window_title', '未知窗口')
        timestamp = capture_data.get('timestamp', datetime.now().isoformat())
        ocr_text = capture_data.get('ocr_text') or capture_data.get('ax_text') or ''

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

            # 2. 调用本地 LLM（带埋点）
            logger.info(f"开始提炼采集记录 {capture_data.get('id')}")
            from monitor.llm_tracker import LLMCallTracker, estimate_tokens
            with LLMCallTracker(
                caller="knowledge",
                model_name=self.model,
                caller_id=str(capture_data.get('id')),
            ) as tracker:
                response = self.client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    format="json",
                    options={"temperature": 0.3, "num_predict": 1024},
                )
                tracker.set_response(response)
                if tracker._prompt_tokens == 0:
                    tracker.set_tokens(
                        prompt=estimate_tokens(SYSTEM_PROMPT + prompt),
                        completion=estimate_tokens(response['message']['content']),
                    )

            # 3. 解析结果
            content = response['message']['content']
            result = _extract_json_object(content)
            if result is None:
                raise json.JSONDecodeError("No valid JSON object found", content, 0)

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
                'observed_at': capture_data.get('ts'),
                'event_time_start': result.get('event_time_start'),
                'event_time_end': result.get('event_time_end'),
                'history_view': bool(result.get('history_view', False)),
                'content_origin': result.get('content_origin'),
                'activity_type': result.get('activity_type'),
                'is_self_generated': False,
                'evidence_strength': result.get('evidence_strength'),
            }

            logger.info(f"成功提炼采集记录 {capture_data.get('id')}: {overview[:50]}...")
            return knowledge

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 响应内容: {content[:500]}")
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

    def extract_merged(
        self,
        captures: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        将多条 captures 合并提炼为一个工作片段知识条目。

        Args:
            captures: 按时间升序排列的 capture 列表

        Returns:
            提炼后的知识条目，包含 capture_ids/start_time/end_time/duration_minutes
        """
        if not captures:
            return None

        # 单条直接走原有逻辑
        if len(captures) == 1:
            result = self.extract_sync(captures[0])
            if result:
                result['capture_ids'] = json.dumps([captures[0]['id']])
                result['start_time'] = captures[0]['ts']
                result['end_time'] = captures[0]['ts']
                result['duration_minutes'] = 0
                result['frag_app_name'] = captures[0].get('app_name')
                result['frag_win_title'] = captures[0].get('window_title')
            return result

        try:
            logger.info("extract_merged 启动: captures=%s", len(captures))
            # 1. 构建合并 prompt：按时间顺序拼接所有 capture 的文本
            merged_blocks = []
            for c in captures:
                text = c.get('ocr_text') or c.get('ax_text') or ''
                if not text.strip():
                    continue
                ts_str = datetime.fromtimestamp(c['ts'] / 1000).strftime('%H:%M:%S')
                app = c.get('app_name', '')
                title = c.get('window_title', '')
                # 每块限制 800 字，避免单条噪声过多
                block = f"[{ts_str}] {app} - {title}\n{text[:800]}"
                merged_blocks.append(block)

            if not merged_blocks:
                return None

            merged_text = "\n\n---\n\n".join(merged_blocks)
            # 总长度限制 6000 字（约 4000 tokens）
            if len(merged_text) > 6000:
                merged_text = merged_text[:6000] + "\n...(已截断)"

            user_prompt = f"以下是一段连续工作片段的采集记录，请提炼：\n\n{merged_text}"

            # 2. 调用 LLM（带埋点）
            logger.info(f"合并提炼 {len(captures)} 条 captures")
            from monitor.llm_tracker import LLMCallTracker, estimate_tokens
            capture_ids_str = ",".join(str(c['id']) for c in captures[:5])
            with LLMCallTracker(
                caller="knowledge",
                model_name=self.model,
                caller_id=f"merge:{capture_ids_str}",
            ) as tracker:
                _sys_prompt = self._build_merge_system_prompt()
                response = self.client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": _sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    format="json",
                    options={"temperature": 0.3, "num_predict": 1024},
                )
                tracker.set_response(response)
                if tracker._prompt_tokens == 0:
                    tracker.set_tokens(
                        prompt=estimate_tokens(_sys_prompt + user_prompt),
                        completion=estimate_tokens(response['message']['content']),
                    )

            # 3. 解析结果
            content = response['message']['content']
            result = _extract_json_object(content)
            if result is None:
                logger.warning("合并提炼返回非预期 JSON，使用兜底 knowledge: content=%s", content[:500])
                return _build_fallback_knowledge(captures, reason='invalid_json')

            overview = result.get('overview', '')
            if not overview or overview == 'SKIP':
                logger.warning("合并提炼未返回有效 overview，使用兜底 knowledge: result=%s", result)
                return _build_fallback_knowledge(captures, reason='empty_overview')

            # 4. 计算片段元数据
            start_time = captures[0]['ts']
            end_time = captures[-1]['ts']
            duration_minutes = int((end_time - start_time) / 60000)

            # 主要应用：出现次数最多的 app_name
            from collections import Counter
            app_counter = Counter(
                c.get('app_name') for c in captures if c.get('app_name')
            )
            frag_app_name = app_counter.most_common(1)[0][0] if app_counter else None

            # 主要窗口：最后一条的 win_title（最能代表当前状态）
            frag_win_title = next(
                (c.get('window_title') for c in reversed(captures) if c.get('window_title')),
                None
            )

            knowledge = {
                'capture_ids': json.dumps([c['id'] for c in captures]),
                'overview': overview,
                'details': result.get('details', ''),
                'entities': json.dumps(result.get('entities', []), ensure_ascii=False),
                'category': result.get('category', '其他'),
                'importance': result.get('importance', 3),
                'occurrence_count': 1,
                'start_time': start_time,
                'end_time': end_time,
                'duration_minutes': duration_minutes,
                'frag_app_name': frag_app_name,
                'frag_win_title': frag_win_title,
                'observed_at': end_time,
                'event_time_start': result.get('event_time_start'),
                'event_time_end': result.get('event_time_end'),
                'history_view': bool(result.get('history_view', False)),
                'content_origin': result.get('content_origin'),
                'activity_type': result.get('activity_type'),
                'is_self_generated': False,
                'evidence_strength': result.get('evidence_strength'),
            }

            logger.info(
                f"合并提炼完成: {len(captures)} captures → 1 knowledge, "
                f"时长={duration_minutes}分钟, overview={overview[:50]}..."
            )
            return knowledge

        except json.JSONDecodeError as e:
            logger.error(f"合并提炼 JSON 解析失败: {e}, 响应内容: {content[:1000]}")
            return None
        except Exception as e:
            logger.error(f"合并提炼失败: {e}")
            return None
