import json

import pytest

from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.services.camera_speech_scoring import apply_camera_speech_score
from app.services.visual_behavior_analysis import summarize_visual_samples
from app.workflow.debate_graph import DebateGraph


def _debate() -> DebateState:
    return DebateState(
        topic="摄像头行为识别测试",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.own_side_only,
        timing=DebateTiming.limited,
        turn_seconds=90,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
        phase="free_debate",
        segment_label="自由辩论 · 反方",
        active_speaker_id="neg_2",
    )


def test_visual_summary_detects_intense_delivery_and_defensive_counter_strategy() -> None:
    samples = [
        {
            "has_face": True,
            "has_pose": True,
            "has_hand": True,
            "confidence": 0.82,
            "eye": 0.76,
            "gesture": 0.48,
            "posture": 0.68,
            "arousal": 0.86,
            "gesture_event": "pointing",
            "emotion": "激动",
        },
        {
            "has_face": True,
            "has_pose": True,
            "has_hand": True,
            "confidence": 0.78,
            "eye": 0.72,
            "gesture": 0.52,
            "posture": 0.7,
            "arousal": 0.8,
            "gesture_event": "chop",
            "emotion": "激动",
        },
    ]

    summary = summarize_visual_samples(samples)

    assert summary.delivery == "激烈"
    assert summary.strategy_mode == "cool_defensive_counter"
    assert "冷静" in summary.opponent_strategy_hint
    assert "逻辑漏洞" in summary.opponent_strategy_hint
    assert summary.dimensions["arousal"] > 0.7


def test_visual_summary_detects_calm_delivery_and_attack_strategy() -> None:
    samples = [
        {
            "has_face": True,
            "has_pose": True,
            "has_hand": True,
            "confidence": 0.76,
            "eye": 0.75,
            "gesture": 0.7,
            "posture": 0.74,
            "arousal": 0.24,
            "gesture_event": "",
            "emotion": "平静",
        }
        for _ in range(4)
    ]

    summary = summarize_visual_samples(samples)

    assert summary.delivery == "冷静"
    assert summary.strategy_mode == "aggressive_attack"
    assert "主动进攻" in summary.opponent_strategy_hint
    assert summary.score_delta > 0


def test_camera_score_uses_multidimensional_window_and_updates_opponent_strategy(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    rows = [
        {
            "ts": 10,
            "has_face": True,
            "has_pose": True,
            "has_hand": True,
            "confidence": 0.8,
            "eye": 0.76,
            "gesture": 0.45,
            "posture": 0.66,
            "arousal": 0.86,
            "gesture_event": "pointing",
            "emotion": "激动",
        },
        {
            "ts": 11,
            "has_face": True,
            "has_pose": True,
            "has_hand": True,
            "confidence": 0.78,
            "eye": 0.7,
            "gesture": 0.5,
            "posture": 0.7,
            "arousal": 0.8,
            "gesture_event": "chop",
            "emotion": "激动",
        },
    ]
    log_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    debate = _debate()

    delta, reason = apply_camera_speech_score(debate, "affirmative", str(log_path), since_ts=9, until_ts=12)

    assert delta != 0
    assert "表达状态：激烈" in reason
    assert "对方策略建议" in reason
    assert debate.score["affirmative"] == pytest.approx(delta)
    assert debate.camera_strategy_hints["negative"]["mode"] == "cool_defensive_counter"
    assert debate.camera_strategy_hints["negative"]["delivery"] == "激烈"
    assert debate.camera_strategy_hints["negative"]["score_delta"] == pytest.approx(delta)


def test_visual_summary_payload_contains_multidimensional_strategy() -> None:
    summary = summarize_visual_samples(
        [
            {
                "has_face": True,
                "has_pose": True,
                "has_hand": True,
                "confidence": 0.83,
                "eye": 0.78,
                "gesture": 0.62,
                "posture": 0.74,
                "arousal": 0.33,
                "stability": 0.81,
                "gesture_event": "open_palm",
                "emotion": "平静",
            }
        ]
    )

    payload = summary.as_payload()

    assert payload["dimensions"]["arousal"] == pytest.approx(0.33)
    assert payload["dimensions"]["stability"] == pytest.approx(0.81)
    assert payload["gesture_counts"] == {"open_palm": 1}
    assert payload["strategy_mode"] == "aggressive_attack"


def test_ai_prompt_includes_camera_strategy_hint_for_opponent() -> None:
    debate = _debate()
    debate.camera_strategy_hints = {
        "negative": {
            "mode": "cool_defensive_counter",
            "hint": "对方刚才情绪激烈，下一轮请冷静拆出逻辑漏洞后反击。",
            "summary": "表达状态：激烈；情绪：激动",
        }
    }

    graph = DebateGraph()
    content = graph._speech_user_content(debate, {"sources": [], "strategy": "测试策略", "stance_action": "反击"})

    assert "摄像头表达状态提示" in content
    assert "冷静拆出逻辑漏洞" in content
