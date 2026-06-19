from unittest.mock import AsyncMock, patch

import pytest

from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, UserMessageCreate, default_agents
from app.services.user_speech_judge import review_user_speech


def _debate() -> DebateState:
    return DebateState(
        topic="人工智能是否提升青少年综合学习能力",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        phase="free_debate",
        segment_label="自由辩论 · 正方",
    )


def _payload(content: str) -> UserMessageCreate:
    return UserMessageCreate(
        speaker_id="aff_1",
        speaker_name="用户辩手",
        side="affirmative",
        content=content,
    )


@pytest.mark.asyncio
async def test_judge_llm_rejects_gibberish():
    debate = _debate()
    mock_raw = (
        '{"acceptable": false, "reason": "乱码灌水", "penalty": 0.5, '
        '"judge_comment": "裁判警告：本轮发言为无意义字符堆砌，未形成有效论点，扣0.5分，请重新发言。"}'
    )
    with patch(
        "app.services.user_speech_judge.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_raw,
    ):
        review = await review_user_speech(debate, _payload("分vu额奴才…"), public_debate=True)
    assert review.acceptable is False
    assert review.reason == "乱码灌水"
    assert "裁判警告" in review.judge_comment


@pytest.mark.asyncio
async def test_judge_llm_accepts_valid_speech():
    debate = _debate()
    mock_raw = '{"acceptable": true, "reason": "", "penalty": 0}'
    with patch(
        "app.services.user_speech_judge.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_raw,
    ):
        review = await review_user_speech(
            debate,
            _payload("对方辩友，你方用少数案例代表普遍现实，这是以偏概全。"),
            public_debate=True,
        )
    assert review.acceptable is True


@pytest.mark.asyncio
async def test_judge_llm_failure_fails_open():
    debate = _debate()
    with patch(
        "app.services.user_speech_judge.chat_completion",
        new_callable=AsyncMock,
        side_effect=Exception("api down"),
    ):
        review = await review_user_speech(debate, _payload("嗯嗯嗯"), public_debate=True)
    assert review.acceptable is True
