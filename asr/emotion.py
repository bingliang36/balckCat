"""
情绪检测模块 - 基于 llm 输出的情绪标记 + 颜文字解析
不再做推理，直接解析 llm 输出中的情绪标记和颜文字
"""

import re


# ══════════════════════════════════════════════════════════════════════════════
#  情绪 → Live2D 表情映射
# ══════════════════════════════════════════════════════════════════════════════

EMOTION_EXPRESSION_MAP = {
    "happy":       "expression2",   # 对应黑猫.model3.json 中的 Name 字段
    "angry":       "expression7",   # heilian
    "sad":         "expression5",   # yanlei
    "surprised":   "expression3",   # quanquanyan
    "embarrassed": "expression6",   # lianhong
}


# ══════════════════════════════════════════════════════════════════════════════
#  颜文字 → 情绪映射（优先匹配）
# ══════════════════════════════════════════════════════════════════════════════

EMOTICON_EMOTION_MAP = {
    # 开心
    "(◕ᴗ◕)":   "happy",
    "(≧▽≦)":   "happy",
    "(*^▽^*)":  "happy",
    "(｡◕‿◕｡)": "happy",
    "♥":        "happy",
    # 生气
    "(# へⁿ )": "angry",
    "(╬ Ò﹏Ó)":  "angry",
    # 伤心
    "呜呜":      "sad",
    "QAQ":       "sad",
    # 惊讶
    "(°ー°〃)":  "surprised",
    "Σ(°△°|||)": "surprised",
    # 害羞
    "(／ω＼)":  "embarrassed",
    "(≿⁠㏨⁠)":  "embarrassed",
}


# ══════════════════════════════════════════════════════════════════════════════
#  标签 → 情绪映射（颜文字没有时 fallback）
# ══════════════════════════════════════════════════════════════════════════════

LABEL_EMOTION_MAP = {
    "【happy】":       "happy",
    "【angry】":       "angry",
    "【sad】":         "sad",
    "【surprised】":   "surprised",
    "【embarrassed】": "embarrassed",
}


# ══════════════════════════════════════════════════════════════════════════════
#  预编译正则
# ══════════════════════════════════════════════════════════════════════════════

# 按长度降序排列，避免短颜文字匹配到长颜文字的前缀
_EMOTICON_KEYS = sorted(EMOTICON_EMOTION_MAP.keys(), key=len, reverse=True)
_EMOTICON_PATTERN = re.compile(
    "|".join(re.escape(e) for e in _EMOTICON_KEYS)
)
_LABEL_PATTERN = re.compile(
    "|".join(re.escape(l) for l in LABEL_EMOTION_MAP.keys())
)


# ══════════════════════════════════════════════════════════════════════════════
#  解析结果数据结构
# ══════════════════════════════════════════════════════════════════════════════

class EmotionTrigger:
    """单个情绪触发点"""

    def __init__(self, char_pos: int, expression_name: str):
        self.char_pos = char_pos        # 在纯文本中的字符位置
        self.expression_name = expression_name  # Live2D 表情名


class EmotionParseResult:
    """一句话的情绪解析结果"""

    def __init__(self, clean_text: str, triggers: list[EmotionTrigger]):
        self.clean_text = clean_text    # 去掉所有情绪标记和颜文字后的纯净文本
        self.triggers = triggers         # 按字符位置升序排列的触发点列表


# ══════════════════════════════════════════════════════════════════════════════
#  解析函数
# ══════════════════════════════════════════════════════════════════════════════

def parse_emotion_from_text(text: str) -> EmotionParseResult:
    """
    解析 llm 输出文本，提取：
    - clean_text：去掉所有情绪标记和颜文字后的纯净文本（供 TTS 朗读）
    - triggers：情绪触发点列表（字符位置 + 对应表情名）

    解析顺序：先找颜文字（优先），再找标签
    返回的 triggers 按字符位置升序排列
    """
    triggers: list[EmotionTrigger] = []

    # 合并所有匹配（颜文字 + 标签），按出现位置排序
    all_matches = []
    for m in _EMOTICON_PATTERN.finditer(text):
        all_matches.append((m.start(), m.end(), m.group(), True))
    for m in _LABEL_PATTERN.finditer(text):
        all_matches.append((m.start(), m.end(), m.group(), False))
    all_matches.sort(key=lambda x: x[0])

    # 逐段重建纯净文本，同时记录触发点
    clean_parts = []
    prev_end = 0

    for start, end, matched_text, is_emoticon in all_matches:
        # 1. 把这段普通字符加入纯净文本
        clean_parts.append(text[prev_end:start])

        # 2. 计算该触发点在纯净文本中的字符位置（此时不含匹配本身）
        clean_char_pos = len("".join(clean_parts))

        # 3. 找到触发表情并记录
        if is_emoticon:
            emotion = EMOTICON_EMOTION_MAP.get(matched_text)
        else:
            emotion = LABEL_EMOTION_MAP.get(matched_text)

        if emotion:
            expression = EMOTION_EXPRESSION_MAP.get(emotion)
            if expression:
                triggers.append(EmotionTrigger(clean_char_pos, expression))

        # 4. 跳过匹配本身（不加入 clean_parts），然后继续
        prev_end = end

    # 剩余部分
    clean_parts.append(text[prev_end:])
    clean_text = "".join(clean_parts)

    return EmotionParseResult(clean_text.strip(), triggers)


# ══════════════════════════════════════════════════════════════════════════════
#  EmotionDetector（兼容旧接口备用）
# ══════════════════════════════════════════════════════════════════════════════

class EmotionDetector:
    """情绪检测器（兼容旧接口）"""

    def __init__(self):
        self.current_emotion = "default"

    def detect(self, text: str) -> str:
        """解析文本中的情绪（兼容旧接口）"""
        result = parse_emotion_from_text(text)
        if result.triggers:
            self.current_emotion = _expression_to_emotion(result.triggers[-1].expression_name)
            return self.current_emotion
        return "default"

    def get_expression_name(self, emotion: str = None) -> str | None:
        """获取 Live2D 表情名（兼容旧接口）"""
        emotion = emotion or self.current_emotion
        return EMOTION_EXPRESSION_MAP.get(emotion)

    def reset(self):
        """重置为默认情绪"""
        self.current_emotion = "default"


def _expression_to_emotion(expression: str) -> str:
    """根据表情名反查情绪"""
    for emotion, expr in EMOTION_EXPRESSION_MAP.items():
        if expr == expression:
            return emotion
    return "default"
