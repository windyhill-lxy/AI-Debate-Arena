import base64
import io
import socket

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.admin_service import admin_debate_detail, admin_list_debates, admin_overview
from app.services.auto_runner import resume_auto, stop_auto
from app.core.custom_prompts import (
    delete_phase_hint,
    get_all_overrides,
    list_all_phases,
    set_phase_hint,
)
router = APIRouter(prefix="/api/admin", tags=["admin"])


class PromptUpdate(BaseModel):
    phase: str
    hint: str


@router.get("/overview")
async def get_overview() -> dict:
    return await admin_overview()


@router.get("/debates")
async def list_debates_admin(limit: int = 50) -> dict:
    items = await admin_list_debates(limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/debates/{debate_id}")
async def get_debate_admin(debate_id: str) -> dict:
    detail = await admin_debate_detail(debate_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    return detail


@router.post("/debates/{debate_id}/stop-auto")
async def stop_debate_auto(debate_id: str) -> dict[str, str]:
    stop_auto(debate_id)
    from app.db.mongo import get_debate, save_debate

    doc = await get_debate(debate_id)
    if doc:
        doc["auto_running"] = False
        await save_debate(doc)
    return {"status": "stopped", "debate_id": debate_id}


@router.post("/debates/{debate_id}/resume-auto")
async def resume_debate_auto(debate_id: str) -> dict[str, str]:
    doc_check = await admin_debate_detail(debate_id)
    if doc_check is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    resume_auto(debate_id)
    return {"status": "resumed", "debate_id": debate_id}


# ── 提示词管理 ────────────────────────────────────────────────────────────────

@router.get("/prompts")
async def get_prompts() -> dict:
    from app.services.debate_schedule import _DEFAULT_HINTS
    phases = list_all_phases()
    overrides = get_all_overrides()
    result = []
    for phase in phases:
        result.append({
            "phase": phase,
            "hint": overrides.get(phase) or _DEFAULT_HINTS.get(phase, ""),
            "is_custom": phase in overrides,
        })
    return {"phases": result, "overrides": overrides}


@router.put("/prompts")
async def update_prompt(body: PromptUpdate) -> dict[str, str]:
    phases = list_all_phases()
    if body.phase not in phases:
        raise HTTPException(status_code=400, detail=f"未知阶段: {body.phase}")
    if not body.hint.strip():
        raise HTTPException(status_code=400, detail="hint 不能为空")
    set_phase_hint(body.phase, body.hint.strip())
    return {"status": "saved", "phase": body.phase}


@router.delete("/prompts/{phase}")
async def reset_prompt(phase: str) -> dict[str, str]:
    deleted = delete_phase_hint(phase)
    if not deleted:
        return {"status": "not_found", "phase": phase}
    return {"status": "reset", "phase": phase}


# ── QR码：局域网扫码访问 ──────────────────────────────────────────────────────

def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@router.get("/qrcode")
async def get_qrcode(frontend_port: int = 5173) -> dict:
    try:
        import qrcode  # type: ignore
    except ImportError:
        raise HTTPException(status_code=503, detail="qrcode 库未安装，请运行: pip install qrcode[pil]")

    lan_ip = _get_lan_ip()
    url = f"http://{lan_ip}:{frontend_port}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"url": url, "lan_ip": lan_ip, "qrcode_b64": b64}


# ── 使用记录 ──────────────────────────────────────────────────────────────────

@router.get("/usage-log")
async def get_usage_log_api(limit: int = 20) -> dict:
    from app.services.usage_log import get_usage_log
    return get_usage_log(limit=limit)
