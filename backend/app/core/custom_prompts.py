"""可持久化的自定义 phase 提示词，存储于 config/custom_prompts.json。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "custom_prompts.json"
_logger = logging.getLogger(__name__)

_ALL_PHASES = [
    "opening_prep", "opening_statement", "argument_review",
    "rebuttal", "rebuttal_review", "cross_examination",
    "segment_summary", "free_prep", "free_debate", "free_review",
    "closing_prep", "closing", "closing_review", "pre_match", "post_match",
]


def _read() -> dict[str, str]:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        _logger.warning("custom_prompts: 读取失败 %s", exc)
    return {}


def _write(data: dict[str, str]) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        _logger.error("custom_prompts: 写入失败 %s", exc)


def get_phase_hint_override(phase: str) -> str | None:
    """返回自定义 hint，若未设置则返回 None。"""
    return _read().get(phase)


def set_phase_hint(phase: str, hint: str) -> None:
    data = _read()
    data[phase] = hint
    _write(data)


def delete_phase_hint(phase: str) -> bool:
    data = _read()
    if phase not in data:
        return False
    del data[phase]
    _write(data)
    return True


def list_all_phases() -> list[str]:
    return list(_ALL_PHASES)


def get_all_overrides() -> dict[str, str]:
    return _read()
