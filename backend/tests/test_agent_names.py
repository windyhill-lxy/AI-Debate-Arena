from pathlib import Path

from app.models import AgentRole, DebateMessage, DebateState, default_agents


FORBIDDEN_OLD_NAMES = ("\u51dbZ", "\u6d45\u7b11")


def test_default_agents_do_not_use_old_placeholder_names() -> None:
    names = {agent.name for agent in default_agents()}

    assert not names.intersection(FORBIDDEN_OLD_NAMES)


def test_frontend_agent_catalog_does_not_use_old_placeholder_names() -> None:
    source = Path("frontend/src/data/agents.js").read_text(encoding="utf-8")

    for old_name in FORBIDDEN_OLD_NAMES:
        assert old_name not in source


def test_legacy_saved_debate_names_are_normalized_on_load() -> None:
    debate = DebateState(
        topic="旧房间昵称迁移",
        visibility="context",
        timing="limited",
        turn_seconds=90,
        format="formal",
        agents=[
            AgentRole(
                id="neg_3",
                name="\u51dbZ",
                side="negative",
                position=3,
                avatar="/agent-z.png",
                model="test",
                persona="反方三辩",
            ),
            AgentRole(
                id="neg_4",
                name="\u6d45\u7b11",
                side="negative",
                position=4,
                avatar="/agent-sweat.png",
                model="test",
                persona="反方四辩",
            ),
        ],
        messages=[
            DebateMessage(
                debate_id="debate-1",
                speaker_id="neg_3",
                speaker_name="\u51dbZ",
                side="negative",
                phase="cross_examination",
                segment_label="质辩",
                content="旧房间消息",
            )
        ],
    )

    assert [agent.name for agent in debate.agents] == ["反方三辩", "反方四辩"]
    assert debate.messages[0].speaker_name == "反方三辩"
