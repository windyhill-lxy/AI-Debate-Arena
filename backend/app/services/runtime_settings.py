from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import get_settings

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


def env_api_keys() -> dict[str, str]:
    settings = get_settings()
    candidates = {
        "deepseek": settings.deepseek_api_key,
        "dashscope": settings.dashscope_api_key,
        "qwen": settings.qwen_api_key,
        "kimi": settings.kimi_api_key_effective,
        "minimax": settings.minimax_api_key_effective,
        "aliyun_ak_id": settings.aliyun_ak_id,
        "aliyun_ak_secret": settings.aliyun_ak_secret,
        "aliyun_isi_appkey": settings.aliyun_isi_appkey,
    }
    return {key: value for key, value in candidates.items() if value}


def merged_api_keys(settings: RuntimeSettings | None = None) -> dict[str, str]:
    runtime = settings or load_runtime_settings()
    merged = env_api_keys()
    merged.update({key: value for key, value in runtime.api_keys.items() if value})
    return merged


def mask_key(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
