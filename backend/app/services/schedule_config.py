from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from app.services.debate_schedule import DebateSegment, seg

_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config" / "schedules"
_CACHE: dict[str, list[DebateSegment]] = {}


@dataclass(frozen=True)
class ScheduleTemplate:
    name: str
    segments: list[DebateSegment]


def _parse_segment(raw: dict) -> DebateSegment:
    side: Literal["affirmative", "negative", "judge", "assistant"] = raw["speaker_side"]
    return seg(
        raw["id"],
        raw["phase"],
        raw["label"],
        raw.get("rules", ""),
        int(raw.get("seconds", 60)),
        side,
        int(raw.get("speaker_position", 0)),
        raw.get("section", "main"),
    )


def load_schedule(template: str = "formal_4v4") -> list[DebateSegment]:
    path = _CONFIG_ROOT / f"{template}.yaml"
    if not path.exists():
        from app.services.debate_schedule import FORMAL_SCHEDULE

        return FORMAL_SCHEDULE

    mtime = path.stat().st_mtime
    cached = _CACHE.get(template)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    segments = [_parse_segment(item) for item in data.get("segments", [])]
    _CACHE[template] = (mtime, segments)
    return segments


def list_schedule_templates() -> list[str]:
    if not _CONFIG_ROOT.exists():
        return ["formal_4v4"]
    return sorted(p.stem for p in _CONFIG_ROOT.glob("*.yaml"))


def list_schedule_templates_meta() -> list[dict]:
    items: list[dict] = []
    for template_id in list_schedule_templates():
        path = _CONFIG_ROOT / f"{template_id}.yaml"
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        segments = data.get("segments") or []
        items.append(
            {
                "id": template_id,
                "title": data.get("title") or template_id,
                "description": data.get("description") or "",
                "segments_count": len(segments),
            }
        )
    return items
