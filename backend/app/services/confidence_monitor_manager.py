from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ops_events import append_ops_event


def _missing_dependencies() -> list[str]:
    required = ("cv2", "mediapipe", "PIL")
    missing: list[str] = []
    for dep in required:
        if importlib.util.find_spec(dep) is None:
            missing.append(dep)
    return missing


@dataclass
class ConfidenceMonitorStatus:
    running: bool
    pid: int | None
    available: bool
    missing_dependencies: list[str]
    last_error: str = ""
    show_landmarks: bool = False
    low_performance: bool = False
    camera_index: int = 0
    session_log_path: str = ""
    session_started_at: float = 0.0
    session_ended_at: float = 0.0
    latest_sample: dict[str, Any] | None = None
    preview_frame_path: str = ""
    preview_frame_updated_at: float = 0.0


class ConfidenceMonitorManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[str] | None = None
        self._last_error = ""
        self._show_landmarks = False
        self._low_performance = False
        self._camera_index = 0
        self._session_log_path = ""
        self._runtime_log_path = ""
        self._preview_frame_path = ""
        self._session_started_at = 0.0
        self._session_ended_at = 0.0

    @staticmethod
    def _tail_runtime_log(path: str, max_lines: int = 6) -> str:
        if not path:
            return ""
        p = Path(path)
        if not p.exists():
            return ""
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return ""
        tail = [line.strip() for line in lines[-max_lines:] if line.strip()]
        return " | ".join(tail)

    @staticmethod
    def _latest_sample(path: str) -> dict[str, Any] | None:
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            return None
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            return None
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                return row
        return None

    def _is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> ConfidenceMonitorStatus:
        with self._lock:
            running = self._is_running()
            if self._proc is not None and not running:
                ret = self._proc.returncode
                self._proc = None
                if ret != 0 and not self._last_error:
                    detail = self._tail_runtime_log(self._runtime_log_path)
                    self._last_error = (
                        f"训练系统异常退出（code={ret}）"
                        + (f"：{detail}" if detail else "，请检查摄像头是否可用或被占用")
                    )
                    append_ops_event("confidence_crash", self._last_error, code=ret, runtime_log=self._runtime_log_path)
            missing = _missing_dependencies()
            return ConfidenceMonitorStatus(
                running=running,
                pid=self._proc.pid if self._proc else None,
                available=not missing,
                missing_dependencies=missing,
                last_error=self._last_error,
                show_landmarks=self._show_landmarks,
                low_performance=self._low_performance,
                camera_index=self._camera_index,
                session_log_path=self._session_log_path,
                session_started_at=self._session_started_at,
                session_ended_at=self._session_ended_at,
                latest_sample=self._latest_sample(self._session_log_path),
                preview_frame_path=self._preview_frame_path,
                preview_frame_updated_at=(
                    Path(self._preview_frame_path).stat().st_mtime if self._preview_frame_path and Path(self._preview_frame_path).exists() else 0.0
                ),
            )

    def start(self, *, show_landmarks: bool = False, camera_index: int = 0, low_performance: bool = False) -> ConfidenceMonitorStatus:
        with self._lock:
            missing = _missing_dependencies()
            self._show_landmarks = show_landmarks
            self._low_performance = low_performance
            self._camera_index = camera_index
            if missing:
                self._last_error = f"缺少依赖: {', '.join(missing)}"
                append_ops_event("confidence_missing_deps", self._last_error)
                return self.status()

            if self._is_running():
                return self.status()

            cmd = [sys.executable, "-m", "app.services.confidence_monitor"]
            if low_performance:
                cmd.append("--low-performance")
            if show_landmarks:
                cmd.append("--show-landmarks")
            started = False
            for idx in dict.fromkeys([camera_index, 0, 1, 2]):
                self._camera_index = idx
                attempt_cmd = [*cmd, "--camera-index", str(idx)]
                self._session_started_at = time.time()
                self._session_ended_at = 0.0
                sessions_dir = Path(__file__).resolve().parents[3] / "data" / "confidence_sessions"
                sessions_dir.mkdir(parents=True, exist_ok=True)
                self._session_log_path = str(sessions_dir / f"session-{int(self._session_started_at)}.jsonl")
                self._runtime_log_path = str(sessions_dir / f"runtime-{int(self._session_started_at)}.log")
                self._preview_frame_path = str(sessions_dir / f"preview-{int(self._session_started_at)}.jpg")
                attempt_cmd.extend(["--session-log-path", self._session_log_path])
                attempt_cmd.extend(["--preview-frame-path", self._preview_frame_path])
                try:
                    runtime_log = Path(self._runtime_log_path)
                    self._proc = subprocess.Popen(  # noqa: S603
                        attempt_cmd,
                        stdout=runtime_log.open("a", encoding="utf-8"),
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                    self._last_error = ""
                    time.sleep(0.6)
                    if self._proc.poll() is None:
                        started = True
                        break
                    code = self._proc.returncode
                    self._proc = None
                    detail = self._tail_runtime_log(self._runtime_log_path)
                    self._last_error = (
                        f"摄像头 index={idx} 打开失败（code={code}）"
                        + (f"：{detail}" if detail else "")
                    )
                except Exception as exc:  # pragma: no cover
                    self._proc = None
                    self._last_error = str(exc)
            if started:
                append_ops_event(
                    "confidence_start",
                    "自信度训练已启动",
                    camera_index=self._camera_index,
                    low_performance=low_performance,
                )
            else:
                append_ops_event("confidence_crash", self._last_error, runtime_log=self._runtime_log_path)
            return self.status()

    def stop(self) -> ConfidenceMonitorStatus:
        with self._lock:
            proc = self._proc
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
            self._proc = None
            self._session_ended_at = time.time()
            append_ops_event("confidence_stop", "自信度训练已停止")
            return self.status()

    def toggle(
        self,
        *,
        enabled: bool,
        show_landmarks: bool = False,
        camera_index: int = 0,
        low_performance: bool = False,
    ) -> ConfidenceMonitorStatus:
        if enabled:
            return self.start(show_landmarks=show_landmarks, camera_index=camera_index, low_performance=low_performance)
        return self.stop()


manager = ConfidenceMonitorManager()


def status_payload(status: ConfidenceMonitorStatus) -> dict[str, Any]:
    sample = status.latest_sample
    reliability_hint = ""
    if status.running and sample:
        if not sample.get("has_face"):
            reliability_hint = "当前未检测到人脸，自信度加减分可能不准确。"
        elif float(sample.get("confidence") or 0) < 0.35:
            reliability_hint = "自信度偏低，发言评分将额外扣减。"
    return {
        "running": status.running,
        "pid": status.pid,
        "available": status.available,
        "missing_dependencies": status.missing_dependencies,
        "last_error": status.last_error,
        "show_landmarks": status.show_landmarks,
        "low_performance": status.low_performance,
        "camera_index": status.camera_index,
        "session_log_path": status.session_log_path,
        "session_started_at": status.session_started_at,
        "session_ended_at": status.session_ended_at,
        "latest_sample": status.latest_sample,
        "preview_frame_path": status.preview_frame_path,
        "preview_frame_updated_at": status.preview_frame_updated_at,
        "confidence_reliability_hint": reliability_hint,
        "confidence_affects_scoring": status.running,
    }
