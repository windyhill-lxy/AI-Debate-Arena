from app.models import DebateMessage, DebateState, default_agents
from app.services.tts_policy import should_synthesize_tts


def _debate() -> DebateState:
    return DebateState(
        topic="裁判 TTS",
        visibility="context",
        timing="limited",
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
    )


def test_judge_pre_match_opening_is_synthesized() -> None:
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="judge",
        speaker_name="紫苑裁判",
        side="judge",
        phase="pre_match",
        segment_label="赛前准备 · 主持开场",
        content="欢迎进入本场辩论。",
    )

    assert should_synthesize_tts(debate, message)


def test_judge_warning_is_synthesized() -> None:
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="judge",
        speaker_name="紫苑裁判",
        side="judge",
        phase="rebuttal",
        segment_label="裁判警告 · 正方二辩发言",
        content="请围绕辩题作答。",
    )

    assert should_synthesize_tts(debate, message)
