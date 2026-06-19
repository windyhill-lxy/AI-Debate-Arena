import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

if os.environ.get("DEBATE_E2E_MOCK") == "1":
    from app.e2e_mock import apply_e2e_llm_patches

    apply_e2e_llm_patches()
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.confidence_monitor import router as confidence_monitor_router
from app.api.tunnel import router as tunnel_router
from app.api.debates import router as debates_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.core.middleware_request_id import RequestIdMiddleware
from app.core.rate_limit import init_rate_limiters
from app.db.mongo import close_mongo, connect_mongo
from app.db.redis_cache import close_redis, connect_redis
from app.db.mongo import storage_mode
from app.services.auto_runner import recover_auto_runners
from app.services.rag import init_vector_index
from app.services.runtime_settings import load_runtime_settings


def _cors_origins() -> list[str]:
    raw = get_settings().cors_origins.strip()
    if not raw:
        return ["http://127.0.0.1:5173"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    init_rate_limiters(
        create_per_min=s.api_rate_limit_create_per_min,
        write_per_min=s.api_rate_limit_write_per_min,
    )
    await connect_mongo()
    await connect_redis()
    init_vector_index()
    resumed = await recover_auto_runners()
    if resumed:
        import logging

        logging.getLogger(__name__).info("recovered %d auto debate runners", resumed)
    yield
    await close_redis()
    await close_mongo()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

app.include_router(debates_router)
app.include_router(admin_router)
app.include_router(confidence_monitor_router)
app.include_router(tunnel_router)


@app.get("/health")
async def health() -> dict[str, str | bool | int]:
    from app.db.mongo import database
    from app.db.redis_cache import redis_connected
    from app.services.confidence_monitor_manager import manager as confidence_monitor_manager

    confidence_status = confidence_monitor_manager.status()
    runtime_settings = load_runtime_settings()
    runtime_keys = runtime_settings.api_keys
    aliyun_ak_id = runtime_keys.get("aliyun_ak_id") or settings.aliyun_ak_id
    aliyun_ak_secret = runtime_keys.get("aliyun_ak_secret") or settings.aliyun_ak_secret
    aliyun_isi_appkey = runtime_keys.get("aliyun_isi_appkey") or settings.aliyun_isi_appkey or settings.nls_app_key
    return {
        "status": "ok",
        "service": settings.app_name,
        "storage": storage_mode(),
        "mongo_connected": database() is not None,
        "redis_connected": redis_connected(),
        "deepseek_configured": bool(runtime_keys.get("deepseek") or settings.deepseek_api_key),
        "deepseek_model": settings.deepseek_model,
        "deepseek_flash_model": settings.deepseek_flash_model,
        "aliyun_tts_enabled": settings.aliyun_tts_enabled,
        "dashscope_configured": bool(runtime_keys.get("dashscope") or settings.dashscope_api_key),
        "aliyun_asr_enabled": settings.aliyun_asr_enabled,
        "aliyun_asr_configured": bool(aliyun_ak_id and aliyun_ak_secret and aliyun_isi_appkey),
        "confidence_monitor_available": confidence_status.available,
        "confidence_monitor_running": confidence_status.running,
        "log_level": settings.log_level,
        "rate_limit_create_per_min": settings.api_rate_limit_create_per_min,
        "rate_limit_write_per_min": settings.api_rate_limit_write_per_min,
    }
