"""
知识提炼模块 - 使用 Qwen3.5-4B 从 OCR 文本中提取结构化知识
"""

import json
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from ollama import Client
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Ollama 未安装，将使用基于规则的简单提炼器")

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个专业的工作记录提炼助手。你的任务是从 OCR 识别的屏幕文本中提取有价值的工作信息。

**提炼规则**：
1. 忽略 UI 元素（按钮、菜单、状态栏等）
2. 提取核心工作内容（会议记录、文档内容、代码片段、聊天记录等）
3. 生成简洁的摘要（50-200 字）
4. 识别关键实体（人名、项目名、时间、地点）
5. 如果内容无价值（纯 UI、重复内容），返回 "SKIP"

**输出格式**（JSON）：
{
  "summary": "简洁摘要",
  "entities": ["实体1", "实体2"],
  "category": "会议|文档|代码|聊天|其他",
  "importance": 1-5
}"""


def simple_extract(capture_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    基于规则的简单知识提炼（当 Ollama 不可用时使用）

    Args:
        capture_data: 采集数据

    Returns:
        提炼后的知识，如果无价值则返回 None
    """
    ocr_text = capture_data.get('ocr_text', '').strip()
    app_name = capture_data.get('app_name', '')
    window_title = capture_data.get('window_title', '')

    # 过滤规则：跳过无价值内容
    if not ocr_text or len(ocr_text) < 20:
        return None

    # 跳过纯 UI 元素
    ui_keywords = ['按钮', '菜单', '工具栏', '状态栏', '关闭', '最小化', '最大化']
    if any(kw in ocr_text for kw in ui_keywords) and len(ocr_text) < 50:
        return None

    # 跳过重复的系统提示
    skip_patterns = [
        r'^(确定|取消|关闭|保存)$',
        r'^(是|否)$',
        r'^\d+$',  # 纯数字
    ]
    if any(re.match(pattern, ocr_text) for pattern in skip_patterns):
        return None

    # 生成摘要（取前 200 字）
    summary = ocr_text[:200]
    if len(ocr_text) > 200:
        summary += "..."

    # 简单实体提取（提取大写单词、中文专有名词）
    entities = []

    # 提取英文大写单词（可能是项目名、公司名）
    english_entities = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', ocr_text)
    entities.extend(english_entities[:5])

    # 提取应用名和窗口标题作为实体
    if app_name:
        entities.append(app_name)
    if window_title and window_title != app_name:
        entities.append(window_title)

    # 去重
    entities = list(set(entities))[:10]

    # 分类判断
    category = '其他'
    if any(kw in app_name.lower() for kw in ['code', 'vscode', 'pycharm', 'idea']):
        category = '代码'
    elif any(kw in app_name.lower() for kw in ['chrome', 'safari', 'firefox', 'edge']):
        category = '浏览器'
    elif any(kw in app_name.lower() for kw in ['word', 'pages', 'notion', 'typora']):
        category = '文档'
    elif any(kw in app_name.lower() for kw in ['wechat', 'slack', 'feishu', 'dingtalk']):
        category = '聊天'
    elif any(kw in app_name.lower() for kw in ['zoom', 'teams', 'meet']):
        category = '会议'

    # 重要性判断（基于文本长度和内容）
    importance = 3  # 默认中等重要
    if len(ocr_text) > 500:
        importance = 4
    if len(ocr_text) > 1000:
        importance = 5
    if len(ocr_text) < 50:
        importance = 2

    return {
        'capture_id': capture_data['id'],
        'summary': summary,
        'entities': json.dumps(entities, ensure_ascii=False),
        'category': category,
        'importance': importance,
    }



class KnowledgeExtractor:
    """知识提炼器"""

    def __init__(self, model: str = "qwen3.5:4b"):
        """
        初始化知识提炼器

        Args:
            model: Ollama 模型名称
        """
        self.model = model
        self.use_ollama = OLLAMA_AVAILABLE

        if OLLAMA_AVAILABLE:
            try:
                self.client = Client()
                logger.info(f"初始化知识提炼器，模型: {model}")
            except Exception as e:
                logger.warning(f"Ollama 客户端初始化失败: {e}，将使用简单提炼器")
                self.use_ollama = False
        else:
            logger.info("使用基于规则的简单知识提炼器")
            self.use_ollama = False

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

    async def extract(self, capture_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从采集数据中提炼知识

        Args:
            capture_data: 采集数据字典，包含 id, app_name, window_title, ocr_text 等

        Returns:
            提炼后的知识字典，如果无价值则返回 None
        """
        # 如果 Ollama 不可用，使用简单提炼器
        if not self.use_ollama:
            logger.info(f"使用简单提炼器处理采集记录 {capture_data.get('id')}")
            result = simple_extract(capture_data)
            if result:
                logger.info(f"成功提炼采集记录 {capture_data.get('id')}: {result['summary'][:50]}...")
            else:
                logger.info(f"采集记录 {capture_data.get('id')} 无价值，跳过")
            return result

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
                format="json",  # 强制 JSON 输出
                options={
                    "temperature": 0.3,  # 降低随机性
                    "num_predict": 256,  # 限制输出长度
                }
            )

            # 3. 解析结果
            content = response['message']['content']
            result = json.loads(content)

            # 4. 跳过无价值内容
            if result.get('summary') == 'SKIP' or not result.get('summary'):
                logger.info(f"采集记录 {capture_data.get('id')} 无价值，跳过")
                return None

            # 5. 返回结构化知识
            knowledge = {
                'capture_id': capture_data['id'],
                'summary': result['summary'],
                'entities': json.dumps(result.get('entities', []), ensure_ascii=False),
                'category': result.get('category', '其他'),
                'importance': result.get('importance', 3),
            }

            logger.info(f"成功提炼采集记录 {capture_data.get('id')}: {knowledge['summary'][:50]}...")
            return knowledge

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 响应内容: {content}")
            return None
        except Exception as e:
            logger.error(f"知识提炼失败: {e}")
            return None

    def extract_sync(self, capture_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """同步版本的提炼方法（用于非异步环境）"""
        # 如果 Ollama 不可用，使用简单提炼器
        if not self.use_ollama:
            logger.info(f"使用简单提炼器处理采集记录 {capture_data.get('id')}")
            result = simple_extract(capture_data)
            if result:
                logger.info(f"成功提炼采集记录 {capture_data.get('id')}: {result['summary'][:50]}...")
            else:
                logger.info(f"采集记录 {capture_data.get('id')} 无价值，跳过")
            return result

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
                    "num_predict": 256,
                }
            )

            # 3. 解析结果
            content = response['message']['content']
            result = json.loads(content)

            # 4. 跳过无价值内容
            if result.get('summary') == 'SKIP' or not result.get('summary'):
                logger.info(f"采集记录 {capture_data.get('id')} 无价值，跳过")
                return None

            # 5. 返回结构化知识
            knowledge = {
                'capture_id': capture_data['id'],
                'summary': result['summary'],
                'entities': json.dumps(result.get('entities', []), ensure_ascii=False),
                'category': result.get('category', '其他'),
                'importance': result.get('importance', 3),
            }

            logger.info(f"成功提炼采集记录 {capture_data.get('id')}: {knowledge['summary'][:50]}...")
            return knowledge

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"知识提炼失败: {e}")
            return None


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 测试数据
    test_capture = {
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
    }

    extractor = KnowledgeExtractor()
    result = extractor.extract_sync(test_capture)

    if result:
        print("提炼结果：")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("无价值内容，已跳过")
