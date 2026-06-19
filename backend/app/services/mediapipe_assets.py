"""下载并缓存 MediaPipe Tasks 模型文件。"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

HOLISTIC_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "holistic_landmarker/holistic_landmarker/float16/1/holistic_landmarker.task"
)
# MediaPipe 原生库在 Windows 上无法加载含中文等非 ASCII 路径的 .task 文件。
MODEL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AI_Debate_Arena" / "mediapipe_models"
HOLISTIC_MODEL_PATH = MODEL_DIR / "holistic_landmarker.task"


def ensure_holistic_model() -> Path:
    if HOLISTIC_MODEL_PATH.exists() and HOLISTIC_MODEL_PATH.stat().st_size > 1024:
        return HOLISTIC_MODEL_PATH
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = HOLISTIC_MODEL_PATH.with_suffix(".task.download")
    urllib.request.urlretrieve(HOLISTIC_MODEL_URL, tmp_path)  # noqa: S310
    tmp_path.replace(HOLISTIC_MODEL_PATH)
    return HOLISTIC_MODEL_PATH
