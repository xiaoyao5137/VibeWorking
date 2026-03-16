"""
工作片段分组器

将连续的 captures 按语义相似度分组为工作片段。
核心原则：不依赖应用/窗口切换判断任务边界，而是用内容语义判断。
"""

import re
import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# 同一工作流中常见的应用组合（来回切换不算任务切换）
RELATED_APP_GROUPS = [
    {'Code', 'Cursor', 'VSCode', 'Visual Studio Code', 'Xcode', 'Terminal', 'iTerm2', 'iTerm'},
    {'Slack', 'DingTalk', 'Feishu', 'WeCom', 'Teams', 'Discord'},
    {'Chrome', 'Safari', 'Firefox', 'Arc', 'Edge'},
    {'Word', 'Pages', 'Notion', 'Obsidian', 'Typora', 'Bear'},
    {'Excel', 'Numbers', 'Google Sheets'},
    {'Figma', 'Sketch', 'Adobe XD'},
]

# 中文停用词
STOP_WORDS = {
    '的', '了', '是', '在', '和', '有', '我', '你', '他', '她', '它',
    '们', '这', '那', '就', '都', '也', '还', '但', '而', '或', '与',
    '对', '从', '到', '以', '为', '被', '把', '让', '使', '将', '已',
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'in',
    'on', 'at', 'by', 'for', 'with', 'as', 'be', 'been', 'being',
}


class FragmentGrouper:
    """
    将连续的 captures 分组为工作片段。

    分组策略（优先级从高到低）：
    1. 时间间隔 > HARD_SPLIT_MINUTES → 强制切断
    2. 语义相似度 >= SAME_TASK_THRESHOLD → 合并
    3. 语义相似度 < DIFF_TASK_THRESHOLD → 切断
    4. 模糊区域 → 用应用回归 + 关键词重叠辅助判断
    """

    HARD_SPLIT_MINUTES = 30     # 超过此时间强制切断
    SOFT_SPLIT_MINUTES = 10     # 超过此时间，要求更高相似度
    SAME_TASK_THRESHOLD = 0.65  # 高于此值：同一件事
    DIFF_TASK_THRESHOLD = 0.40  # 低于此值：不同的事
    SAME_TASK_THRESHOLD_SOFT = 0.72  # 间隔较长时的更高阈值
    MIN_GROUP_WAIT = 3          # 至少积累3条才开始处理，避免切断进行中的任务

    def __init__(self, embedding_model=None):
        self.embedding_model = embedding_model

    def group_captures(self, captures: list[dict]) -> list[list[dict]]:
        """
        输入：按时间升序排列的 captures 列表
        输出：分组后的片段列表，每个片段是一组 captures

        注意：最后一组可能是进行中的任务，调用方应自行决定是否处理。
        """
        if not captures:
            return []

        if len(captures) == 1:
            return [captures]

        # 批量向量化（有 embedding_model 时）
        vectors = self._batch_encode(captures)

        groups: list[list[dict]] = []
        current_group: list[dict] = [captures[0]]
        current_vectors: list = [vectors[0]] if vectors else []

        for i in range(1, len(captures)):
            curr = captures[i]
            prev = captures[i - 1]
            gap_minutes = (curr['ts'] - prev['ts']) / 60000

            # 规则1：强制切断
            if gap_minutes > self.HARD_SPLIT_MINUTES:
                groups.append(current_group)
                current_group = [curr]
                current_vectors = [vectors[i]] if vectors else []
                continue

            # 规则2/3/4：语义判断
            if vectors:
                should_merge = self._semantic_judge(
                    curr_vector=vectors[i],
                    group_vectors=current_vectors,
                    gap_minutes=gap_minutes,
                    current_group=current_group,
                    curr_capture=curr,
                )
            else:
                # 无向量模型时，退化为关键词判断
                should_merge = self._keyword_judge(current_group, curr)

            if should_merge:
                current_group.append(curr)
                if vectors:
                    current_vectors.append(vectors[i])
            else:
                groups.append(current_group)
                current_group = [curr]
                current_vectors = [vectors[i]] if vectors else []

        if current_group:
            groups.append(current_group)

        logger.info(f"分组完成: {len(captures)} 条 captures → {len(groups)} 个片段")
        return groups

    # ─────────────────────────────────────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────────────────────────────────────

    def _batch_encode(self, captures: list[dict]) -> Optional[list]:
        """批量向量化所有 captures"""
        if not self.embedding_model:
            return None
        try:
            texts = [self._get_semantic_text(c) for c in captures]
            embeddings = self.embedding_model.encode(texts)
            return [np.array(e.vector) for e in embeddings]
        except Exception as ex:
            logger.warning(f"向量化失败，退化为关键词判断: {ex}")
            return None

    def _get_semantic_text(self, capture: dict) -> str:
        """提取用于语义判断的文本，过滤短行噪声"""
        text = capture.get('ax_text') or capture.get('ocr_text') or ''
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 10]
        return ' '.join(lines)[:512]

    def _compute_theme_vector(self, vectors: list) -> np.ndarray:
        """
        计算当前片段的"主题向量"。
        最近3条 capture 权重更高，反映当前任务焦点。
        """
        if len(vectors) == 1:
            return vectors[0]

        n = len(vectors)
        weights = np.ones(n) * 0.5
        # 最近3条加权
        for j, idx in enumerate(range(max(0, n - 3), n)):
            weights[idx] = [0.3, 0.35, 0.4][j] if n >= 3 else 0.5
        weights = weights / weights.sum()

        stacked = np.stack(vectors, axis=0)
        theme = np.average(stacked, axis=0, weights=weights)
        norm = np.linalg.norm(theme)
        return theme / norm if norm > 0 else theme

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _semantic_judge(
        self,
        curr_vector: np.ndarray,
        group_vectors: list,
        gap_minutes: float,
        current_group: list[dict],
        curr_capture: dict,
    ) -> bool:
        """基于语义相似度判断是否合并"""
        theme_vector = self._compute_theme_vector(group_vectors)
        similarity = self._cosine_similarity(curr_vector, theme_vector)

        # 间隔较长时要求更高相似度
        threshold = (
            self.SAME_TASK_THRESHOLD_SOFT
            if gap_minutes > self.SOFT_SPLIT_MINUTES
            else self.SAME_TASK_THRESHOLD
        )

        if similarity >= threshold:
            return True
        elif similarity < self.DIFF_TASK_THRESHOLD:
            return False
        else:
            # 模糊区域：用上下文辅助判断
            return self._check_context_continuity(current_group, curr_capture)

    def _check_context_continuity(
        self,
        current_group: list[dict],
        new_capture: dict,
    ) -> bool:
        """
        模糊区域辅助判断：
        1. 应用回归：新 capture 的 app 在当前片段中出现过（来回切换场景）
        2. 关键词重叠：新 capture 与片段近期内容有2个以上关键词重叠
        """
        # 1. 应用回归
        group_apps = {c.get('app_name') for c in current_group if c.get('app_name')}
        if new_capture.get('app_name') in group_apps:
            return True

        # 2. 关键词重叠（只看最近5条，避免早期内容干扰）
        recent_text = ' '.join(
            c.get('ax_text') or c.get('ocr_text') or ''
            for c in current_group[-5:]
        )
        new_text = new_capture.get('ax_text') or new_capture.get('ocr_text') or ''

        group_kw = self._extract_keywords(recent_text)
        new_kw = self._extract_keywords(new_text)

        if len(group_kw & new_kw) >= 2:
            return True

        return False

    def _keyword_judge(self, current_group: list[dict], new_capture: dict) -> bool:
        """无向量模型时的退化判断（仅关键词 + 应用回归）"""
        return self._check_context_continuity(current_group, new_capture)

    def _extract_keywords(self, text: str) -> set:
        """提取关键词：中文2字以上词组 + 英文3字以上单词，过滤停用词"""
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text)
        return {w for w in words if w.lower() not in STOP_WORDS}
