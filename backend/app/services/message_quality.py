"""用户/辩手发言质量检测（灌水、乱码、偏离辩题）。"""

from __future__ import annotations

import re

_DEBATE_SIGNAL_RE = re.compile(
    r"对方辩友|我方|贵方|辩题|论点|论据|立论|反驳|质询|盘问|总结|因此|所以|请问|因为|但是|然而|"
    r"人工智能|AI|青少年|学习|能力|依赖|思考|工具|教育|标准|事实|逻辑|数据|案例|证据|"
    r"机制|产品|引导|习惯|批判|验证|替代|反馈"
)

_WEAK_PATTERNS = (
    "我认为你说的对",
    "我同意",
    "不知道",
    "随便",
    "无所谓",
    "都行",
    "嗯",
    "啊",
)


def low_information_reason(content: str, *, public_debate: bool = False) -> str | None:
    text = (content or "").strip()
    compact = re.sub(r"[*_`>#\-\[\]\(\)\s]+", "", text)
    if len(compact) < 8:
        return "发言过短或信息量不足"

    meaningful_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text)
    if len(meaningful_chars) < 8:
        return "发言缺少有效文字"

    unique_ratio = len(set(meaningful_chars)) / max(1, len(meaningful_chars))
    if unique_ratio < 0.15:
        return "发言疑似重复灌水"

    normalized = "".join(meaningful_chars)
    for unit_size in range(1, min(6, len(normalized) // 2 + 1)):
        if len(normalized) % unit_size == 0:
            unit = normalized[:unit_size]
            if unit * (len(normalized) // unit_size) == normalized:
                return "发言疑似重复灌水"

    lower = text.lower()
    if any(token in text or token in lower for token in _WEAK_PATTERNS):
        return "发言没有给出有效论点"

    latin_mash = re.findall(r"[\u4e00-\u9fff][a-zA-Z]{1,4}[\u4e00-\u9fff]", text)
    if len(latin_mash) >= 2 and len(compact) >= 16:
        return "发言疑似乱码灌水"

    chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    if len(compact) >= 24 and len(set(chinese_runs)) < 3:
        return "发言缺乏有效论述结构"

    if public_debate and len(compact) >= 20 and not _DEBATE_SIGNAL_RE.search(text):
        if not re.search(r"^##\s", text, re.M):
            return "发言未围绕辩题展开"

    return None


def looks_low_information_message(text: str) -> bool:
    return low_information_reason(text, public_debate=False) is not None
