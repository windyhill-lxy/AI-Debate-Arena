import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.network_diag import run_network_diagnose
from app.services import tunnel_ngrok
from app.services.tunnel_service import (
    get_status,
    get_tunnel_proxy,
    get_tunnel_provider,
    list_providers,
    set_tunnel_provider,
    set_tunnel_proxy,
    start_tunnel,
    stop_tunnel,
    verify_tunnel,
)

router = APIRouter(prefix="/api/tunnel", tags=["tunnel"])


class TunnelProxyPayload(BaseModel):
    proxy: str | None = None


class TunnelProviderPayload(BaseModel):
    provider: str = "auto"


class NgrokTokenPayload(BaseModel):
    authtoken: str | None = None


@router.get("/status")
async def tunnel_status() -> dict[str, object]:
    return get_status().to_dict()


@router.get("/verify")
async def tunnel_verify() -> dict[str, object]:
    return verify_tunnel().to_dict()


@router.get("/diagnose")
async def tunnel_diagnose(quick: bool = True) -> dict[str, object]:
    return run_network_diagnose(quick=quick)


@router.get("/proxy")
async def tunnel_proxy_get() -> dict[str, object]:
    return {"proxy": get_tunnel_proxy()}


@router.post("/proxy")
async def tunnel_proxy_set(payload: TunnelProxyPayload) -> dict[str, object]:
    return {"proxy": set_tunnel_proxy(payload.proxy)}


@router.get("/providers")
async def tunnel_providers() -> dict[str, object]:
    return list_providers()


@router.post("/provider")
async def tunnel_provider_set(payload: TunnelProviderPayload) -> dict[str, object]:
    return {"provider": set_tunnel_provider(payload.provider), **list_providers()}


@router.get("/ngrok-token")
async def ngrok_token_get() -> dict[str, object]:
    token = tunnel_ngrok.get_ngrok_authtoken()
    return {"configured": bool(token), "masked": f"{token[:6]}…" if token and len(token) > 8 else None}


@router.post("/ngrok-token")
async def ngrok_token_set(payload: NgrokTokenPayload) -> dict[str, object]:
    token = tunnel_ngrok.set_ngrok_authtoken(payload.authtoken)
    return {"configured": bool(token), **list_providers()}


@router.post("/start")
async def tunnel_start(force: bool = False) -> dict[str, object]:
    status = await asyncio.to_thread(start_tunnel, force=force)
    return status.to_dict()


@router.post("/stop")
async def tunnel_stop() -> dict[str, object]:
    return stop_tunnel().to_dict()
