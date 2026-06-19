from app.services.judge_report import _is_report_complete, _missing_report_sections


def test_missing_report_sections_detects_absent_headers():
    text = "## 胜负判定\n\n正方胜。\n\n## 三条主战场\n\n争点一。"
    missing = _missing_report_sections(text)
    assert "## 最佳辩手" in missing
    assert "## 改进建议" in missing


def test_is_report_complete_requires_all_sections_and_terminal_punctuation():
    complete = (
        "## 胜负判定\n\n反方胜。\n\n"
        "## 三条主战场\n\n1. 标准之争。\n\n"
        "## 最佳辩手\n\n反方四辩。\n\n"
        "## 正方最大失误\n\n偷换概念。\n\n"
        "## 反方最大失误\n\n举例不当。\n\n"
        "## 改进建议\n\n加强证据核验。"
    )
    assert _is_report_complete(complete) is True

    truncated = complete.replace("加强证据核验。", "加强证据核验")
    assert _is_report_complete(truncated) is False
