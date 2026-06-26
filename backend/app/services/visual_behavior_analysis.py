from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any


DIMENSION_KEYS = ("confidence", "eye", "gesture", "posture", "arousal", "stability")
AGGRESSIVE_EVENTS = {"pointing", "chop", "fast_wave"}
OPEN_EVENTS = {"open_palm", "raised_hand", "shrug"}
INTENSE_EMOTIONS = {"激动", "愤怒", "紧张", "焦虑"}
CALM_EMOTIONS = {"平静", "冷静", "专注"}
GESTURE_LABELS = {
    "shrug": "摊手",
    "pointing": "指人",
    "chop": "切分手势",
    "fast_wave": "快速挥手",
    "open_palm": "开放手势",
    "raised_hand": "举手",
}


@dataclass
class VisualBehaviorSummary:
    sample_count: int = 0
    reliability: str = "none"
    confidence_label: str = "未知"
    delivery: str = "未知"
    emotion: str = "未知"
    strategy_mode: str = "neutral"
    opponent_strategy_hint: str = ""
    score_delta: float = 0.0
    score_reason: str = ""
    dimensions: dict[str, float] = field(default_factory=dict)
    gesture_counts: dict[str, int] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "reliability": self.reliability,
            "confidence_label": self.confidence_label,
            "delivery": self.delivery,
            "emotion": self.emotion,
            "strategy_mode": self.strategy_mode,
            "opponent_strategy_hint": self.opponent_strategy_hint,
            "score_delta": self.score_delta,
            "score_reason": self.score_reason,
            "dimensions": self.dimensions,
            "gesture_counts": self.gesture_counts,
            "summary": self.short_summary(),
        }

    def short_summary(self) -> str:
        if self.sample_count <= 0:
            return "暂无摄像头表达样本"
        parts = [
            f"表达状态：{self.delivery}",
            f"情绪：{self.emotion}",
            f"自信：{self.confidence_label}",
            f"可信度：{self.reliability}",
        ]
        if self.gesture_counts:
            gesture_text = "、".join(
                f"{GESTURE_LABELS.get(name, name)}×{count}" for name, count in self.gesture_counts.items()
            )
            parts.append(f"手势：{gesture_text}")
        return "；".join(parts)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [_as_float(row.get(key)) for row in rows if row.get(key) is not None]
    return round(mean(values), 4) if values else 0.0


def _event_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        event = str(row.get("gesture_event") or "").strip()
        if not event:
            continue
        counts[event] = counts.get(event, 0) + 1
    return counts


def _mode_text(rows: list[dict[str, Any]], key: str) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: item[1])[0]


def _reliability(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "none"
    n = len(rows)
    face_ratio = sum(1 for row in rows if row.get("has_face")) / n
    pose_ratio = sum(1 for row in rows if row.get("has_pose")) / n
    hand_ratio = sum(1 for row in rows if row.get("has_hand")) / n
    if face_ratio >= 0.7 and (pose_ratio >= 0.45 or hand_ratio >= 0.45):
        return "high"
    if face_ratio >= 0.45:
        return "medium"
    if pose_ratio >= 0.45 or hand_ratio >= 0.45:
        return "low"
    return "none"


def _confidence_label(
    *,
    confidence: float,
    eye: float,
    has_confidence: bool,
    has_eye: bool,
) -> str:
    confidence_known = has_confidence or has_eye
    if not confidence_known:
        return "未知"
    if confidence >= 0.68 and (eye >= 0.55 or not has_eye):
        return "自信"
    if confidence < 0.45 or (has_eye and eye < 0.38):
        return "不自信"
    return "稳定"


def _delivery_label(
    *,
    rows: list[dict[str, Any]],
    arousal: float,
    stability: float,
    aggressive_count: int,
    emotion: str,
    has_arousal: bool,
) -> str:
    intense_by_events = aggressive_count >= max(1, len(rows) // 4)
    intense_by_emotion = emotion in INTENSE_EMOTIONS
    if (has_arousal and arousal >= 0.68) or intense_by_events or intense_by_emotion:
        return "激烈"
    if has_arousal and arousal <= 0.42 and stability >= 0.55 and aggressive_count == 0:
        return "冷静"
    if emotion in CALM_EMOTIONS and stability >= 0.5 and aggressive_count == 0:
        return "冷静"
    return "稳定"


def _strategy_for_delivery(delivery: str) -> tuple[str, str]:
    if delivery == "激烈":
        return (
            "cool_defensive_counter",
            "对方刚才表达较激烈，下一轮请保持冷静，先拆出逻辑漏洞、概念跳跃或证据缺口，再做防御反击。",
        )
    if delivery == "冷静":
        return (
            "aggressive_attack",
            "对方刚才表达较冷静，下一轮请主动进攻，压缩其论证空间，连续追问定义、证据和因果链。",
        )
    return (
        "balanced_probe",
        "对方表达较稳定，下一轮请保持均衡攻防，先试探薄弱环节，再选择重点推进。",
    )


def _legacy_event_score(open_count: int, aggressive_count: int) -> tuple[float, list[str]]:
    delta = 0.0
    reasons: list[str] = []
    if open_count:
        bonus = min(0.3, open_count * 0.1)
        delta += bonus
        reasons.append(f"开放/摊手手势 {open_count} 次 +{bonus:.2f}")
    if aggressive_count:
        penalty = min(0.6, aggressive_count * 0.2)
        delta -= penalty
        reasons.append(f"指人/压迫性手势 {aggressive_count} 次 -{penalty:.2f}")
    return delta, reasons


def _multidimensional_score(
    *,
    confidence: float,
    eye: float,
    gesture: float,
    posture: float,
    arousal: float,
    stability: float,
    has_metric: dict[str, bool],
    open_count: int,
    aggressive_count: int,
) -> tuple[float, list[str]]:
    score_delta = 0.0
    reasons: list[str] = []

    if has_metric["confidence"] and confidence >= 0.75 and (eye >= 0.6 or not has_metric["eye"]):
        score_delta += 0.18
        reasons.append("镜头自信稳定 +0.18")
    elif has_metric["confidence"] and confidence < 0.38:
        score_delta -= 0.18
        reasons.append("镜头自信偏低 -0.18")

    if has_metric["eye"] and eye >= 0.68:
        score_delta += 0.05
        reasons.append("眼神稳定 +0.05")
    elif has_metric["eye"] and eye < 0.35:
        score_delta -= 0.08
        reasons.append("眼神游离 -0.08")

    if has_metric["posture"] and posture >= 0.68:
        score_delta += 0.08
        reasons.append("姿态稳定 +0.08")
    elif has_metric["posture"] and posture < 0.42:
        score_delta -= 0.1
        reasons.append("姿态不稳 -0.10")

    if stability >= 0.72:
        score_delta += 0.06
        reasons.append("整体稳定性好 +0.06")
    elif has_metric["stability"] and stability < 0.38:
        score_delta -= 0.08
        reasons.append("整体稳定性不足 -0.08")

    if open_count:
        bonus = min(0.12, open_count * 0.04)
        score_delta += bonus
        reasons.append(f"开放手势 {open_count} 次 +{bonus:.2f}")
    if aggressive_count:
        penalty = min(0.2, aggressive_count * 0.06)
        score_delta -= penalty
        reasons.append(f"压迫性手势 {aggressive_count} 次 -{penalty:.2f}")

    if has_metric["arousal"] and arousal >= 0.8 and aggressive_count:
        score_delta -= 0.08
        reasons.append("情绪过激 -0.08")
    elif has_metric["arousal"] and 0.35 <= arousal <= 0.65 and confidence >= 0.55:
        score_delta += 0.06
        reasons.append("情绪节奏平稳 +0.06")
    elif has_metric["arousal"] and arousal < 0.28 and confidence >= 0.65:
        score_delta += 0.04
        reasons.append("表达冷静克制 +0.04")

    return score_delta, reasons


def summarize_visual_samples(samples: list[dict[str, Any]]) -> VisualBehaviorSummary:
    rows = [row for row in samples if isinstance(row, dict)]
    if not rows:
        return VisualBehaviorSummary()

    dimensions = {key: _mean(rows, key) for key in DIMENSION_KEYS}
    has_metric = {key: any(row.get(key) is not None for row in rows) for key in DIMENSION_KEYS}
    confidence = dimensions.get("confidence", 0.0)
    eye = dimensions.get("eye", 0.0)
    gesture = dimensions.get("gesture", 0.0)
    posture = dimensions.get("posture", 0.0)
    arousal = dimensions.get("arousal", 0.0)
    if has_metric["stability"]:
        stability = dimensions.get("stability", 0.0)
    elif has_metric["gesture"] or has_metric["posture"]:
        stability = min(value for value, known in ((gesture, has_metric["gesture"]), (posture, has_metric["posture"])) if known)
    else:
        stability = 0.0
    dimensions["stability"] = round(stability, 4)

    counts = _event_counts(rows)
    aggressive_count = sum(counts.get(event, 0) for event in AGGRESSIVE_EVENTS)
    open_count = sum(counts.get(event, 0) for event in OPEN_EVENTS)
    emotion = _mode_text(rows, "emotion")
    delivery = _delivery_label(
        rows=rows,
        arousal=arousal,
        stability=stability,
        aggressive_count=aggressive_count,
        emotion=emotion,
        has_arousal=has_metric["arousal"],
    )
    if not emotion:
        emotion = "激动" if delivery == "激烈" else "平静" if delivery == "冷静" else "专注"

    strategy_mode, opponent_strategy_hint = _strategy_for_delivery(delivery)
    confidence_label = _confidence_label(
        confidence=confidence,
        eye=eye,
        has_confidence=has_metric["confidence"],
        has_eye=has_metric["eye"],
    )

    if not any(has_metric.values()):
        score_delta, reasons = _legacy_event_score(open_count, aggressive_count)
    else:
        score_delta, reasons = _multidimensional_score(
            confidence=confidence,
            eye=eye,
            gesture=gesture,
            posture=posture,
            arousal=arousal,
            stability=stability,
            has_metric=has_metric,
            open_count=open_count,
            aggressive_count=aggressive_count,
        )

    score_delta = round(max(-0.5, min(0.5, score_delta)), 2)
    score_reason = "；".join(reasons)
    return VisualBehaviorSummary(
        sample_count=len(rows),
        reliability=_reliability(rows),
        confidence_label=confidence_label,
        delivery=delivery,
        emotion=emotion,
        strategy_mode=strategy_mode,
        opponent_strategy_hint=opponent_strategy_hint,
        score_delta=score_delta,
        score_reason=score_reason,
        dimensions=dimensions,
        gesture_counts=counts,
    )
