from app.services.llm import strip_model_reasoning
from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.workflow.debate_graph import (
    _apply_phase_speech_limits,
    _cross_examination_mode,
    _framework_looks_incomplete,
    _looks_incomplete,
    _max_sentences_for_phase,
)


def _debate(phase: str = "opening_statement") -> DebateState:
    return DebateState(
        topic="测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=180,
        format="formal",
        phase=phase,
        segment_seconds=180,
        agents=default_agents(),
        workflow=workflow_template(),
    )
from app.services.message_quality import looks_low_information_message as _looks_low_information_message


def test_cross_examination_mode_distinguishes_question_and_response() -> None:
    assert _cross_examination_mode("正方三辩盘问") == "question"
    assert _cross_examination_mode("反方回应盘问") == "respond"
    assert _cross_examination_mode("正方回应质询") == "respond"


def test_low_information_message_detection() -> None:
    assert _looks_low_information_message("我认为你说的对")
    assert _looks_low_information_message("嗯嗯嗯嗯")
    assert not _looks_low_information_message("我方认为AI应该以反问式反馈保留试错链条，并要求提供样本边界。")


def test_framework_incomplete_detects_missing_layers() -> None:
    aff = "论证框架分三层递进：第一，个性化反馈。第二，拓展资源。"
    neg = "论证框架分两层：第一，AI即时反馈剥夺建构。"
    assert _framework_looks_incomplete(aff) is True
    assert _framework_looks_incomplete(neg) is True
    done = "论证框架分两层：第一，A。第二，B。因此我方立场成立。"
    assert _framework_looks_incomplete(done) is False


def test_looks_incomplete_flags_unfinished_framework_even_with_period() -> None:
    text = "论证框架分两层：第一，AI即时反馈有问题。心理学告诉我们深度需要困难。"
    assert _looks_incomplete(text) is True


def test_apply_phase_speech_limits_keeps_normal_opening() -> None:
    debate = _debate("opening_statement")
    text = "论证框架分三层递进：第一，A。第二，B。第三，C。因此我方成立。"
    assert _apply_phase_speech_limits(text, debate) == text


def test_apply_phase_speech_limits_trims_only_free_debate() -> None:
    debate = _debate("free_debate")
    debate.phase = "free_debate"
    text = "第一句。第二句。"
    assert _apply_phase_speech_limits(text, debate) == "第一句。"


def test_opening_statement_sentence_budget_scales_with_time() -> None:
    assert _max_sentences_for_phase("opening_statement", 180) >= 18
    assert _max_sentences_for_phase("opening_statement", 180) > 12
    assert _max_sentences_for_phase("free_debate", 30) == 1


def test_strip_model_reasoning_removes_think_blocks() -> None:
    text = "<think>这里是模型思考，不应公开。</think>\n## 质询\n请问对方如何证明这个机制必然成立？"
    cleaned = strip_model_reasoning(text)
    assert "模型思考" not in cleaned
    assert "<think>" not in cleaned
    assert "## 质询" in cleaned
