from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

RUNTIME_SETTINGS_PATH = Path(__file__).resolve().parents[3] / "data" / "runtime_settings.json"


class RuntimeSettings(BaseModel):
    api_keys: dict[str, str] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)


def load_runtime_settings() -> RuntimeSettings:
    if not RUNTIME_SETTINGS_PATH.exists():
        return RuntimeSettings()
    try:
        data = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return RuntimeSettings()
    return RuntimeSettings.model_validate(data)


def apply_runtime_settings(settings: RuntimeSettings) -> RuntimeSettings:
    RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_SETTINGS_PATH.write_text(
        json.dumps(settings.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return settings


def mask_key(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
