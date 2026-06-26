from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.confidence_monitor_manager import manager, status_payload
from app.services.confidence_report import (
    build_llm_summary,
    build_programmatic_metrics,
    compare_with_previous_session,
    load_confidence_samples,
)

router = APIRouter(prefix="/api/confidence-monitor", tags=["confidence-monitor"])


class ConfidenceTogglePayload(BaseModel):
    enabled: bool = True
    show_landmarks: bool = False
    camera_index: int = Field(default=0, ge=0, le=10)
    low_performance: bool = True


class ConfidenceReportPayload(BaseModel):
    max_samples: int = Field(default=600, ge=60, le=5000)


@router.get("/status")
async def confidence_monitor_status() -> dict:
    status = status_payload(manager.status())
    latest = status.get("latest_sample") or {}
    visual_summary = status.get("visual_summary") or {}
    if latest:
        has_face = bool(latest.get("has_face"))
        has_pose = bool(latest.get("has_pose"))
        has_hand = bool(latest.get("has_hand"))
        confidence_reliability = "high" if (has_face and (has_pose or has_hand)) else ("medium" if has_face else "low")
        status["confidence_reliability"] = confidence_reliability
        if confidence_reliability == "high":
            status["confidence_reliability_hint"] = "评分可信度高：已检测到脸部与身体/手势关键点。"
        elif confidence_reliability == "medium":
            status["confidence_reliability_hint"] = "评分可信度中：当前主要依据脸部特征，手势/姿态信息较少。"
        else:
            status["confidence_reliability_hint"] = "评分可信度低：关键点检测不足，请调整取景。"
    else:
        status["confidence_reliability"] = "low"
        status["confidence_reliability_hint"] = "暂无样本，无法判断评分可信度。"

    if visual_summary:
        status["fixed_realtime_hint"] = (
            f"{visual_summary.get('summary', '')}；"
            f"本次表达计分 {float(visual_summary.get('score_delta') or 0):+.2f}。"
        )
        status["opponent_strategy_hint"] = visual_summary.get("opponent_strategy_hint", "")
    elif latest:
        gesture = float(latest.get("gesture", 0.0))
        if gesture < 0.4:
            status["fixed_realtime_hint"] = "手势偏急，建议放慢手部动作并减少抖动。"
        else:
            status["fixed_realtime_hint"] = "手势较稳定，继续保持句间手势节奏。"
    else:
        status["fixed_realtime_hint"] = "暂无实时样本。"
    return status


@router.get("/preview.jpg")
async def confidence_monitor_preview() -> FileResponse:
    status = manager.status()
    preview_path = Path(status.preview_frame_path) if status.preview_frame_path else None
    if preview_path is None or not preview_path.exists():
        raise HTTPException(status_code=404, detail="preview_not_ready")
    return FileResponse(
        path=preview_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.post("/toggle")
async def confidence_monitor_toggle(payload: ConfidenceTogglePayload) -> dict:
    status = manager.toggle(
        enabled=payload.enabled,
        show_landmarks=payload.show_landmarks,
        camera_index=payload.camera_index,
        low_performance=payload.low_performance,
    )
    return status_payload(status)


@router.get("/metrics")
async def confidence_monitor_metrics() -> dict:
    status = manager.status()
    if not status.session_log_path:
        return {"status": "no_session", "metrics": build_programmatic_metrics([])}
    samples = load_confidence_samples(status.session_log_path)
    return {
        "status": "ok",
        "running": status.running,
        "metrics": build_programmatic_metrics(samples),
    }


@router.post("/report")
async def confidence_monitor_report(payload: ConfidenceReportPayload) -> dict:
    status = manager.status()
    if not status.session_log_path:
        return {
            "status": "no_session",
            "metrics": build_programmatic_metrics([]),
            "llm_report": "暂无练习会话，请先开始训练。",
        }
    samples = load_confidence_samples(status.session_log_path)
    if payload.max_samples and len(samples) > payload.max_samples:
        samples = samples[-payload.max_samples :]
    metrics = build_programmatic_metrics(samples)
    compare = compare_with_previous_session(status.session_log_path, metrics)
    llm_report = await build_llm_summary(samples, metrics)
    return {
        "status": "ok",
        "running": status.running,
        "metrics": metrics,
        "compare": compare,
        "llm_report": llm_report,
    }
