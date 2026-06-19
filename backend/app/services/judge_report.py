from app.models import DebateState
from app.services.confidence_monitor_manager import manager as confidence_manager
from app.services.confidence_report import build_programmatic_metrics, load_confidence_samples
from app.services.llm import DeepSeekError, chat_completion, format_history, resolve_model

_FINAL_REPORT_SECTIONS = (
    "## 胜负判定",
    "## 三条主战场",
    "## 最佳辩手",
    "## 正方最大失误",
    "## 反方最大失误",
    "## 改进建议",
)
_FINAL_REPORT_MAX_TOKENS = 5500
_FINAL_REPORT_CONTINUATION_TOKENS = 2800


def _missing_report_sections(text: str) -> list[str]:
    return [section for section in _FINAL_REPORT_SECTIONS if section not in text]


def _is_report_complete(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    if _missing_report_sections(stripped):
        return False
    if stripped[-1] not in "。！？.!?）)」』":
        return False
    return True


def _confidence_summary_for_report() -> str:
    status = confidence_manager.status()
    if not status.session_log_path:
        return (
            "未开启摄像头训练：用户发言自信度按默认良好档（+0.10）计入实时比分，"
            "表达与临场状态在终局总结中作辅助参考。"
        )
    samples = load_confidence_samples(status.session_log_path)
    metrics = build_programmatic_metrics(samples)
    if metrics.get("sample_count", 0) <= 0:
        return "摄像头训练已开启，但暂无有效样本。"
    avg = metrics.get("averages", {})
    stability = metrics.get("stability", {})
    return (
        "摄像头训练参数："
        f"样本 {metrics.get('sample_count', 0)} 条，时长 {metrics.get('duration_sec', 0.0)} 秒；"
        f"平均 eye={avg.get('eye', 0.0):.2f}, gesture={avg.get('gesture', 0.0):.2f}, "
        f"posture={avg.get('posture', 0.0):.2f}, confidence={avg.get('confidence', 0.0):.2f}；"
        f"低稳定占比 eye={stability.get('eye_low_ratio', 0.0):.2f}, "
        f"gesture={stability.get('gesture_low_ratio', 0.0):.2f}, "
        f"posture={stability.get('posture_low_ratio', 0.0):.2f}；"
        f"举手次数 {metrics.get('raised_hand_count', 0)}。"
    )


def _user_speech_digest(debate: DebateState) -> str:
    """汇总全部用户/真人辩手发言，含不当发言标记（供终局裁判批评）。"""
    lines: list[str] = []
    for msg in debate.messages:
        if msg.speech_flag is None:
            continue
        flag = "【不当发言已扣分】" if msg.speech_flag == "inappropriate" else ""
        reason = f"（{msg.review_reason}）" if msg.review_reason else ""
        label = msg.segment_label or msg.phase
        lines.append(f"- {msg.speaker_name} · {label}{flag}{reason}：{msg.content[:280]}")
    if not lines:
        return "本场无用户真人发言记录。"
    return "\n".join(lines)


async def generate_final_report(debate: DebateState) -> str:
    """终局 LLM 全盘总结：胜负、主战场、最佳辩手、双方失误。"""
    score_aff = debate.score.get("affirmative", 0)
    score_neg = debate.score.get("negative", 0)
    history = format_history(debate.messages[-32:])
    user_digest = _user_speech_digest(debate)
    confidence_summary = _confidence_summary_for_report()

    prompt = [
        {
            "role": "system",
            "content": (
                "你是辩论赛裁判长，需输出**终局全盘总结**（Markdown）。"
                "必须包含以下二级标题：## 胜负判定、## 三条主战场、## 最佳辩手、## 正方最大失误、## 反方最大失误、## 改进建议。"
                "评分时参考以下维度：① 优手表现（论点清晰、证据具体、引用有出处）② 总结完整性（是否回应全场关键争点）③ 论点明确度（是否有三个清晰论点）；每个维度均需在报告中体现。"
                "## 最佳辩手：须写出具体**表扬理由**（论点清晰度 / 证据质量 / 临场反应），点名称赞突出表现的发言片段。"
                "## 正方最大失误 和 ## 反方最大失误：须点出**逻辑漏洞类型**（偷换概念/因果谬误/以偏概全/举例不当）并说明为何导致失分；"
                "如有用户发言标注【不当发言已扣分】，须在对应方失误中点名批评，但不重复赛中扣分细节。"
                "## 改进建议：按辩手逐条给出具体改进方向，并纠正本场出现的逻辑漏洞，提供正确论证思路。"
                "不得替任何一方继续辩论；可引用上文比分与环节表现。"
                "若提供了摄像头训练参数，请把它当作「表达与临场状态」的辅助证据之一，"
                "权重低于逻辑与证据质量，不可喧宾夺主。"
                "六个二级标题必须全部写完并以完整句子收束，不得中途截断；"
                "各节可精炼但不可省略「## 反方最大失误」「## 改进建议」。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{debate.topic}\n"
                f"比分：正方 {score_aff:.1f} · 反方 {score_neg:.1f}\n"
                f"当前环节：{debate.segment_label}\n\n"
                f"近期发言摘要：\n{history}\n\n"
                f"用户真人发言全记录：\n{user_digest}\n\n"
                f"自信度训练摘要：\n{confidence_summary}"
            ),
        },
    ]
    model = resolve_model(phase="post_match", speaker_id="judge")
    try:
        report = (
            await chat_completion(
                prompt,
                model=model,
                temperature=0.45,
                max_tokens=_FINAL_REPORT_MAX_TOKENS,
                debate_id=debate.id,
                operation="final_report",
            )
        ).strip()
        if not _is_report_complete(report):
            missing = _missing_report_sections(report)
            tail = report[-400:] if len(report) > 400 else report
            continuation_prompt = prompt + [
                {"role": "assistant", "content": report},
                {
                    "role": "user",
                    "content": (
                        "上文终局总结未写完或结尾不完整。"
                        f"{'缺少章节：' + '、'.join(missing) if missing else '请补全最后未完成的段落。'}"
                        "请从断点继续，补全剩余内容；不要重复已写章节，"
                        "务必以完整句号结束全文。"
                        f"\n\n已写结尾片段：\n…{tail}"
                    ),
                },
            ]
            tail_text = (
                await chat_completion(
                    continuation_prompt,
                    model=model,
                    temperature=0.35,
                    max_tokens=_FINAL_REPORT_CONTINUATION_TOKENS,
                    debate_id=debate.id,
                    operation="final_report_continue",
                )
            ).strip()
            if tail_text:
                report = f"{report.rstrip()}\n\n{tail_text}".strip()
        return report
    except DeepSeekError:
        winner = "正方" if score_aff >= score_neg else "反方"
        return (
            f"## 胜负判定\n\n{winner} 以 {max(score_aff, score_neg):.1f} : {min(score_aff, score_neg):.1f} 领先。\n\n"
            "## 三条主战场\n\n1. 评价标准是否统一\n2. 证据可验证性\n3. 对青少年学习能力的因果论证\n\n"
            "## 最佳辩手\n\n待人工复核（模型暂不可用）。\n\n"
            "## 改进建议\n\n加强引用资料编号与回应针对性；如已开启摄像头训练，可结合稳定性指标优化临场表达。"
        )
