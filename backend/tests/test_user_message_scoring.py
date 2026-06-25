from unittest.mock import patch

from app.models import DebateMessage, DebateMode, DebateState, DebateTiming, DebateVisibility, Source, default_agents
from app.services.user_message_scoring import confidence_score_adjustment, score_user_public_message


def _debate() -> DebateState:
    return DebateState(
        topic="测试",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
    )


def test_user_message_gets_base_score():
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="用户",
        side="affirmative",
        content="对方辩友，我方认为人工智能在正确引导下可以提升青少年综合学习能力。",
        phase="free_debate",
        segment_label="自由辩论",
    )
    with patch("app.services.user_message_scoring.confidence_score_adjustment", return_value=(0.0, "")):
        score_user_public_message(debate, message, [Source(id="kb-1", title="资料", excerpt="x")])
    assert message.score_delta is not None
    assert debate.score["affirmative"] > 0
    assert "自信度" not in (message.score_reason or "")


def test_confidence_bonus_applied_to_user_score():
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="用户",
        side="affirmative",
        content="对方辩友，我方认为人工智能在正确引导下可以提升青少年综合学习能力。",
        phase="free_debate",
        segment_label="自由辩论",
    )
    with patch(
        "app.services.user_message_scoring.confidence_score_adjustment",
        return_value=(0.25, "自信度优秀（80%）+0.25"),
    ):
        score_user_public_message(debate, message, [])
    assert "自信度优秀" in (message.score_reason or "")
    assert message.score_delta >= 1.2


def test_confidence_adjustment_is_neutral_when_camera_is_not_running():
    with patch("app.services.confidence_monitor_manager.manager.status") as status:
        status.return_value.running = False
        status.return_value.latest_sample = None

        delta, reason = confidence_score_adjustment()

    assert delta == 0
    assert reason == ""
