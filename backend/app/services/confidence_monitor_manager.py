from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ops_events import append_ops_event
from app.services.visual_behavior_analysis import summarize_visual_samples

DEFAULT_LOW_PERFORMANCE = True


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
    visual_summary: dict[str, Any] | None = None
    preview_frame_path: str = ""
    preview_frame_updated_at: float = 0.0


class ConfidenceMonitorManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[str] | None = None
        self._last_error = ""
        self._show_landmarks = False
        self._low_performance = DEFAULT_LOW_PERFORMANCE
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
    def _load_recent_samples(path: str, max_lines: int = 80) -> list[dict[str, Any]]:
        if not path:
            return []
        p = Path(path)
        if not p.exists():
            return []
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []
        rows: list[dict[str, Any]] = []
        for line in lines[-max_lines:]:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    @classmethod
    def _latest_sample(cls, path: str) -> dict[str, Any] | None:
        rows = cls._load_recent_samples(path, max_lines=80)
        return rows[-1] if rows else None

    def _is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _terminate_proc(self, proc: subprocess.Popen[str], timeout: float = 3.0) -> None:
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
            return
        except Exception:
            pass
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            proc.kill()

    def _sync_process_state(self) -> bool:
        running = self._is_running()
        if self._proc is None or running:
            return running

        ret = self._proc.returncode
        self._proc = None
        self._session_ended_at = self._session_ended_at or time.time()
        if ret != 0 and not self._last_error:
            detail = self._tail_runtime_log(self._runtime_log_path)
            self._last_error = (
                f"识别进程异常退出（code={ret}）"
                + (f"：{detail}" if detail else "，请检查摄像头是否可用或被占用。")
            )
            append_ops_event("confidence_crash", self._last_error, code=ret, runtime_log=self._runtime_log_path)
        return False

    def status(self) -> ConfidenceMonitorStatus:
        with self._lock:
            running = self._sync_process_state()
            missing = _missing_dependencies()
            latest_sample = self._latest_sample(self._session_log_path)
            recent_samples = self._load_recent_samples(self._session_log_path)
            visual_summary = summarize_visual_samples(recent_samples).as_payload() if recent_samples else None
            preview_updated_at = 0.0
            if self._preview_frame_path:
                preview = Path(self._preview_frame_path)
                if preview.exists():
                    try:
                        preview_updated_at = preview.stat().st_mtime
                    except OSError:
                        preview_updated_at = 0.0
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
                latest_sample=latest_sample,
                visual_summary=visual_summary,
                preview_frame_path=self._preview_frame_path,
                preview_frame_updated_at=preview_updated_at,
            )

    def start(
        self,
        *,
        show_landmarks: bool = False,
        camera_index: int = 0,
        low_performance: bool = DEFAULT_LOW_PERFORMANCE,
    ) -> ConfidenceMonitorStatus:
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
            if self._proc is not None:
                self._proc = None

            cmd = [sys.executable, "-m", "app.services.confidence_monitor"]
            if low_performance:
                cmd.append("--low-performance")
            if show_landmarks:
                cmd.append("--show-landmarks")

            sessions_dir = Path(__file__).resolve().parents[3] / "data" / "confidence_sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            self._last_error = ""
            started = False
            for idx in dict.fromkeys([camera_index, 0, 1, 2]):
                started_at = time.time()
                session_tag = f"{int(started_at * 1000)}-{idx}"
                self._camera_index = idx
                self._session_started_at = started_at
                self._session_ended_at = 0.0
                self._session_log_path = str(sessions_dir / f"session-{session_tag}.jsonl")
                self._runtime_log_path = str(sessions_dir / f"runtime-{session_tag}.log")
                self._preview_frame_path = str(sessions_dir / f"preview-{session_tag}.jpg")
                attempt_cmd = [
                    *cmd,
                    "--camera-index",
                    str(idx),
                    "--session-log-path",
                    self._session_log_path,
                    "--preview-frame-path",
                    self._preview_frame_path,
                ]
                try:
                    runtime_log = Path(self._runtime_log_path)
                    self._proc = subprocess.Popen(  # noqa: S603
                        attempt_cmd,
                        stdout=runtime_log.open("a", encoding="utf-8"),
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                    time.sleep(0.9)
                    if self._proc.poll() is None:
                        started = True
                        self._last_error = ""
                        break
                    code = self._proc.returncode
                    self._proc = None
                    detail = self._tail_runtime_log(self._runtime_log_path)
                    self._last_error = f"摄像头 index={idx} 打开失败（code={code}）" + (f"：{detail}" if detail else "")
                except Exception as exc:  # pragma: no cover
                    self._proc = None
                    self._last_error = str(exc)

            if started:
                append_ops_event(
                    "confidence_start",
                    "自信度识别已启动",
                    camera_index=self._camera_index,
                    low_performance=low_performance,
                )
            else:
                self._session_ended_at = time.time()
                append_ops_event("confidence_crash", self._last_error, runtime_log=self._runtime_log_path)
            return self.status()

    def stop(self) -> ConfidenceMonitorStatus:
        with self._lock:
            proc = self._proc
            if proc is not None:
                self._terminate_proc(proc)
            self._proc = None
            self._session_ended_at = time.time()
            self._last_error = ""
            append_ops_event("confidence_stop", "自信度识别已停止")
            return self.status()

    def toggle(
        self,
        *,
        enabled: bool,
        show_landmarks: bool = False,
        camera_index: int = 0,
        low_performance: bool = DEFAULT_LOW_PERFORMANCE,
    ) -> ConfidenceMonitorStatus:
        if enabled:
            return self.start(show_landmarks=show_landmarks, camera_index=camera_index, low_performance=low_performance)
        return self.stop()


manager = ConfidenceMonitorManager()


def status_payload(status: ConfidenceMonitorStatus) -> dict[str, Any]:
    sample = status.latest_sample or {}
    visual_summary = status.visual_summary or sample.get("visual_summary")
    reliability_hint = ""
    if status.running and sample:
        if not sample.get("has_face"):
            reliability_hint = "当前未检测到人脸，表达评分可信度较低，请调整取景。"
        elif float(sample.get("confidence") or 0) < 0.35:
            reliability_hint = "自信度偏低，本次发言评分会适度扣分。"
        elif visual_summary:
            reliability_hint = f"表达状态：{visual_summary.get('summary', '已获取多维样本')}"
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
        "visual_summary": visual_summary,
        "preview_frame_path": status.preview_frame_path,
        "preview_frame_updated_at": status.preview_frame_updated_at,
        "confidence_reliability_hint": reliability_hint,
        "confidence_affects_scoring": status.running,
    }
