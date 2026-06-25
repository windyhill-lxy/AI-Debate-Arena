import json

import pytest

from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.services.camera_speech_scoring import apply_camera_speech_score


def _debate() -> DebateState:
    return DebateState(
        topic="摄像头评分测试",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.own_side_only,
        timing=DebateTiming.limited,
        turn_seconds=90,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
    )


def test_no_camera_samples_do_not_change_score(tmp_path) -> None:
    debate = _debate()
    delta, reason = apply_camera_speech_score(debate, "affirmative", "")
    assert delta == 0
    assert reason == ""
    assert debate.score["affirmative"] == 0


def test_shrug_bonus_and_pointing_penalty_are_applied(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    rows = [
        {"ts": 1, "gesture_event": "shrug"},
        {"ts": 2, "gesture_event": "pointing"},
        {"ts": 3, "gesture_event": "pointing"},
    ]
    log_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    debate = _debate()

    delta, reason = apply_camera_speech_score(debate, "affirmative", str(log_path), since_ts=0, until_ts=4)

    assert delta == pytest.approx(-0.3)
    assert "摊手" in reason
    assert "指人" in reason
    assert debate.score["affirmative"] == pytest.approx(-0.3)
