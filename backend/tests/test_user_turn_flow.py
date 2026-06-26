import pytest
from datetime import UTC, datetime

from app.models import (
    DebateMode,
    DebateMessage,
    DebateState,
    DebateTiming,
    DebateVisibility,
    OnlineParticipant,
    UserMessageCreate,
    default_agents,
    workflow_template,
)
from app.services.debate_schedule import apply_segment, get_segment, init_schedule
from app.services.user_speech_judge import UserSpeechReview


class _CameraStatus:
    running = True
    latest_sample = {"has_face": True}
    session_log_path = "camera.jsonl"
    session_started_at = 100.0


def _online_team_discussion_debate() -> DebateState:
    debate = DebateState(
        topic="用户发言流程测试",
        mode=DebateMode.online_match,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
        awaiting_user=True,
        active_speaker_id="aff_1",
    )
    init_schedule(debate)
    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing affirmative opening discussion segment")
    debate.awaiting_user = True
    debate.active_speaker_id = "aff_1"
    debate.participants.extend(
        [
            OnlineParticipant(id="p1", name="正方一辩", side="affirmative", position=1),
            OnlineParticipant(id="p2", name="正方二辩", side="affirmative", position=2),
        ]
    )
    return debate


@pytest.mark.asyncio
async def test_accept_user_message_waits_next_team_debater_without_advancing(monkeypatch) -> None:
    from app.services import user_turn_flow

    debate = _online_team_discussion_debate()
    before_index = debate.schedule_index

    monkeypatch.setattr(user_turn_flow, "retrieve_sources", lambda *_args, **_kwargs: [])

    async def no_argument_bank_update(_debate: DebateState, _message: DebateMessage):
        return {"affirmative": 0, "negative": 0}

    monkeypatch.setattr(user_turn_flow, "add_message_arguments_to_bank_with_ai_titles", no_argument_bank_update)

    result = await user_turn_flow.accept_user_message(
        debate,
        UserMessageCreate(
            participant_id="p1",
            speaker_name="正方一辩",
            side="affirmative",
            position=1,
            content="我先把框架收住，二辩接定义。",
        ),
        debate.participants[0],
        review=UserSpeechReview(acceptable=True),
        public_debate=False,
        internal=True,
    )

    assert result.schedule_index == before_index
    assert result.awaiting_user is True
    assert result.active_speaker_id == "aff_2"
    assert result.messages[-1].speaker_id == "aff_1"


def test_public_scoring_uses_windowed_camera_without_latest_frame_double_count(monkeypatch) -> None:
    from app.services import user_turn_flow

    debate = DebateState(
        topic="窗口摄像头评分测试",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
        awaiting_user=True,
        active_speaker_id="aff_1",
        awaiting_user_since=datetime.fromtimestamp(120, tz=UTC),
        human_timeout_penalty_enabled=False,
    )
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="用户",
        side="affirmative",
        content="我方用证据回应对方逻辑漏洞。",
        phase="free_debate",
        segment_label="自由辩论",
    )
    latest_calls: list[bool] = []
    window_calls: list[tuple[str, float | None]] = []

    def fake_public_score(_debate, _message, _sources, *, include_latest_camera=True):
        latest_calls.append(include_latest_camera)
        _debate.score[_message.side] += 1.0
        _message.score_delta = 1.0
        _message.score_reason = "基础 +1.00"

    def fake_camera_score(_debate, side, path, *, since_ts=None, until_ts=None):
        window_calls.append((path, since_ts))
        _debate.score[side] += 0.2
        return 0.2, "多维摄像头 +0.20"

    monkeypatch.setattr(user_turn_flow, "score_user_public_message", fake_public_score)
    monkeypatch.setattr(user_turn_flow, "apply_camera_speech_score", fake_camera_score)

    user_turn_flow.apply_user_message_scoring(
        debate,
        message,
        UserSpeechReview(acceptable=True),
        public_debate=True,
        camera_status=_CameraStatus(),
    )

    assert latest_calls == [False]
    assert window_calls == [("camera.jsonl", pytest.approx(120.0))]
    assert debate.score["affirmative"] == pytest.approx(1.2)
    assert message.score_delta == pytest.approx(1.2)
