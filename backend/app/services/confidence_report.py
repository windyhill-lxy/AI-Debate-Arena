from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from app.services.llm import DeepSeekError, chat_completion, resolve_model
from app.services.visual_behavior_analysis import summarize_visual_samples


def load_confidence_samples(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _safe_mean(rows: list[dict[str, Any]], key: str) -> float:
    vals = [float(r.get(key, 0.0)) for r in rows if r.get(key) is not None]
    return round(mean(vals), 4) if vals else 0.0


def build_programmatic_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "sample_count": 0,
            "duration_sec": 0.0,
            "averages": {
                "eye": 0.0,
                "gesture": 0.0,
                "posture": 0.0,
                "confidence": 0.0,
                "arousal": 0.0,
                "stability": 0.0,
            },
            "stability": {"eye_low_ratio": 0.0, "gesture_low_ratio": 0.0, "posture_low_ratio": 0.0},
            "raised_hand_count": 0,
            "visual_summary": summarize_visual_samples([]).as_payload(),
            "fixed_feedback": "暂无足够数据，请先完成一段练习。",
            "fixed_suggestions": [],
        }

    duration_sec = float(samples[-1].get("elapsed_sec", 0.0))
    avg_eye = _safe_mean(samples, "eye")
    avg_gesture = _safe_mean(samples, "gesture")
    avg_posture = _safe_mean(samples, "posture")
    avg_confidence = _safe_mean(samples, "confidence")
    avg_arousal = _safe_mean(samples, "arousal")
    avg_stability = _safe_mean(samples, "stability")
    visual_summary = summarize_visual_samples(samples)

    n = max(1, len(samples))
    eye_low_ratio = round(sum(1 for s in samples if float(s.get("eye", 0.0)) < 0.45) / n, 4)
    gesture_low_ratio = round(sum(1 for s in samples if float(s.get("gesture", 0.0)) < 0.45) / n, 4)
    posture_low_ratio = round(sum(1 for s in samples if float(s.get("posture", 0.0)) < 0.5) / n, 4)
    raised_hand_count = sum(1 for s in samples if bool(s.get("raised_hand")))

    suggestions: list[str] = []
    if eye_low_ratio > 0.35:
        suggestions.append("眼神稳定度偏低：建议发言时固定注视镜头 2-3 秒再切换视线。")
    if gesture_low_ratio > 0.35:
        suggestions.append("手势平滑度偏低：建议减少高频小幅抖动，改为每句配一个慢动作手势。")
    if posture_low_ratio > 0.35:
        suggestions.append("姿态稳定性偏低：建议双肩保持水平，避免身体长期向一侧倾斜。")
    if avg_arousal > 0.72:
        suggestions.append("情绪强度偏高：建议先放慢语速，再用证据和逻辑漏洞完成反击。")
    if not suggestions:
        suggestions.append("整体参数稳定：继续保持当前节奏，可尝试增强停顿层次和关键词手势。")

    if avg_confidence >= 0.75:
        fixed_feedback = "程序性评价：表现良好，参数稳定，具备较好的镜头表达感。"
    elif avg_confidence >= 0.6:
        fixed_feedback = "程序性评价：整体中上，建议优先优化手势与眼神同步。"
    else:
        fixed_feedback = "程序性评价：稳定性仍需提升，建议先练习慢速表达和固定姿态。"

    return {
        "sample_count": len(samples),
        "duration_sec": round(duration_sec, 3),
        "averages": {
            "eye": avg_eye,
            "gesture": avg_gesture,
            "posture": avg_posture,
            "confidence": avg_confidence,
            "arousal": avg_arousal,
            "stability": avg_stability,
        },
        "stability": {
            "eye_low_ratio": eye_low_ratio,
            "gesture_low_ratio": gesture_low_ratio,
            "posture_low_ratio": posture_low_ratio,
        },
        "raised_hand_count": raised_hand_count,
        "visual_summary": visual_summary.as_payload(),
        "fixed_feedback": fixed_feedback,
        "fixed_suggestions": suggestions,
    }


def compare_with_previous_session(current_path: str, current_metrics: dict[str, Any]) -> dict[str, Any]:
    p = Path(current_path) if current_path else None
    if p is None or not p.exists():
        return {"available": False}
    sessions_dir = p.parent
    current_name = p.name
    candidates = sorted(sessions_dir.glob("session-*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)
    prev = next((item for item in candidates if item.name != current_name), None)
    if prev is None:
        return {"available": False}
    prev_samples = load_confidence_samples(str(prev))
    prev_metrics = build_programmatic_metrics(prev_samples)
    curr_avg = current_metrics.get("averages", {}) or {}
    prev_avg = prev_metrics.get("averages", {}) or {}
    keys = ("confidence", "eye", "gesture", "posture", "arousal", "stability")
    delta = {k: round(float(curr_avg.get(k, 0.0)) - float(prev_avg.get(k, 0.0)), 4) for k in keys}
    return {
        "available": True,
        "previous_session": prev.name,
        "delta": delta,
        "previous_sample_count": int(prev_metrics.get("sample_count", 0)),
    }


async def build_llm_summary(samples: list[dict[str, Any]], metrics: dict[str, Any]) -> str:
    if not samples:
        return "暂无练习数据，无法生成深度总结。"
    tail = samples[-20:]
    prompt = {
        "metrics": metrics,
        "tail_samples": tail,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是演讲与辩论训练教练。根据给定的姿态、手势、眼神、情绪强度、稳定性轨迹，给出结构化复盘："
                "1) 本次表现总评；2) 三个关键问题（按优先级）；3) 可执行改进动作（每条具体到行为）；"
                "4) 下一次练习目标。要求：中文，客观，避免空话，控制在 250-450 字。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(prompt, ensure_ascii=False),
        },
    ]
    try:
        return await chat_completion(
            messages,
            model=resolve_model(phase="post_match"),
            temperature=0.45,
            max_tokens=900,
            operation="confidence_report",
        )
    except DeepSeekError as exc:
        return f"大模型总结暂不可用（{exc}）。可先根据程序性建议继续练习。"
