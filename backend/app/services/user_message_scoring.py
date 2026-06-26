"""用户公开发言的裁判评分（含自信度摄像头加成）。"""

from __future__ import annotations

from app.models import DebateMessage, DebateState, Source


def confidence_score_adjustment() -> tuple[float, str]:
    from app.services.confidence_monitor_manager import manager

    status = manager.status()
    if not status.running:
        return 0.0, ""
    sample = status.latest_sample or {}
    if not sample:
        return 0.0, ""
    if not sample.get("has_face"):
        return 0.0, ""
    confidence = float(sample.get("confidence") or 0.0)
    if confidence >= 0.75:
        return 0.25, f"自信度优秀（{confidence:.0%}）+0.25"
    if confidence >= 0.55:
        return 0.1, f"自信度良好（{confidence:.0%}）+0.10"
    if confidence < 0.35:
        return -0.35, f"自信度偏低（{confidence:.0%}）-0.35"
    return 0.0, ""


_AUTHORITY_KEYWORDS = [
    "世界卫生组织", "世卫", "教育部", "中国科学院", "国家统计局", "联合国", "央视", "新华社",
    "哈佛大学", "北京大学", "清华大学", "斯坦福大学", "麻省理工", "世界银行", "世贸组织",
    "nature", "science", "lancet", "《自然》", "《科学》",
]

_ANALOGY_KEYWORDS = ["就像", "好比", "如同", "犹如", "仿佛", "好似", "宛如", "相当于"]

_CITATION_FORMAT_PATTERN = r"(?:[一-龥A-Za-z]+机构|[一-龥A-Za-z]+大学|[一-龥A-Za-z]+研究所).{0,6}(?:\d{4}年|研究|调查|报告|数据)表明"
_EVENT_PATTERN = r"\d{4}年.{1,20}(?:事件|案例|研究|发布|发现|提出|证明|显示)"


def _count_analogies(text: str) -> int:
    import re as _re
    return sum(1 for kw in _ANALOGY_KEYWORDS if kw in text)


def _has_citation_format(text: str) -> bool:
    import re as _re
    return bool(_re.search(_CITATION_FORMAT_PATTERN, text))


def _has_specific_event(text: str) -> bool:
    import re as _re
    return bool(_re.search(_EVENT_PATTERN, text))


def _has_authority_source(text: str) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in _AUTHORITY_KEYWORDS)


def score_user_public_message(
    debate: DebateState,
    message: DebateMessage,
    sources: list[Source],
    *,
    include_latest_camera: bool = True,
) -> None:
    reasons: list[str] = ["用户发言基础 +1.00"]
    delta = 1.0

    source_bonus = min(len(sources), 3) * 0.12
    if source_bonus:
        delta += source_bonus
        reasons.append(f"引用资料 {len(sources)} 条 +{source_bonus:.2f}")

    length_bonus = 0.15 if 60 <= len(message.content) <= 420 else 0.0
    if length_bonus:
        delta += length_bonus
        reasons.append(f"篇幅适中 +{length_bonus:.2f}")

    if _has_citation_format(message.content):
        delta += 0.12
        reasons.append("含规范引用格式（xx机构/xx年研究）+0.12")

    if _has_specific_event(message.content):
        delta += 0.10
        reasons.append("含具体真实事件引用 +0.10")

    if _has_authority_source(message.content):
        delta += 0.05
        reasons.append("引用大众化权威机构 +0.05")

    analogy_count = _count_analogies(message.content)
    if analogy_count >= 3:
        penalty = -0.08
        delta += penalty
        reasons.append(f"过多比喻/类比（{analogy_count}处）逻辑性弱 {penalty:.2f}")

    if include_latest_camera:
        conf_delta, conf_reason = confidence_score_adjustment()
        if conf_delta:
            delta += conf_delta
            reasons.append(conf_reason)

    message.score_reason = "；".join(reasons)
    if message.side in debate.score:
        debate.score[message.side] += delta
        message.score_delta = round(delta, 2)
