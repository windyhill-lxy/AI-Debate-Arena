import asyncio
import base64
import logging
import re
from uuid import uuid4
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.models import AgentRole, DebateMessage
from app.services.runtime_settings import load_runtime_settings

logger = logging.getLogger(__name__)

# 阿里云 Qwen3-TTS-Instruct：接口报错写 600，实际更接近 512 token；中文按保守估算
API_HARD_MAX = 600
TOKEN_SAFE_CHAR_CAP = 240  # 约 240 汉字 ≈ 480 token，低于 512 上限

DEBATE_SPEED_HINT = "快语速，辩论现场女声，吐字清晰。"

# 辩论现场只需朗读核心内容，避免长文拆成多段 API 导致界面长时间卡在「合成中」
MAX_TTS_TOTAL_CHARS = 480
MAX_TTS_CHUNKS = 3
TTS_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=15.0, pool=10.0)
TTS_CHUNK_DEADLINE_SEC = 50.0


class TTSError(Exception):
    pass


@dataclass(frozen=True)
class TTSProfile:
    voice: str
    emotion: str
    role: str

    @property
    def instructions(self) -> str:
        # 尽量短，避免与正文合计超过 600
        return f"{self.role}，情感{self.emotion}。{DEBATE_SPEED_HINT}分段合成时前后音色、语速、停顿保持一致。"


VOICE_PROFILES: dict[str, TTSProfile] = {
    "aff_1": TTSProfile("Maia", "neutral", "正方一辩"),
    "aff_2": TTSProfile("Vivian", "surprised", "正方二辩"),
    "aff_3": TTSProfile("Momo", "happy", "正方三辩"),
    "aff_4": TTSProfile("Bellona", "neutral", "正方四辩"),
    "neg_1": TTSProfile("Cherry", "neutral", "反方一辩"),
    "neg_2": TTSProfile("Stella", "angry", "反方二辩"),
    "neg_3": TTSProfile("Bella", "surprised", "反方三辩"),
    "neg_4": TTSProfile("Katerina", "neutral", "反方四辩"),
    "judge": TTSProfile("Serena", "neutral", "主席裁判"),
}

DEFAULT_PROFILE = TTSProfile("Cherry", "neutral", "旁白")


def tts_profile_for_agent(agent: AgentRole | None) -> TTSProfile:
    if agent is None:
        return DEFAULT_PROFILE
    return VOICE_PROFILES.get(agent.id, DEFAULT_PROFILE)


def markdown_to_speech_text(markdown: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", markdown)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_>#\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _estimate_tokens(text: str) -> int:
    total = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            total += 2
        elif ch.isalnum():
            total += 1
        else:
            total += 1
    return total


def _effective_text_limit(profile: TTSProfile) -> int:
    """动态扣除 instructions，并受 token 上限约束。"""
    char_budget = max(100, API_HARD_MAX - len(profile.instructions) - 32)
    return min(char_budget, TOKEN_SAFE_CHAR_CAP)


def build_qwen_tts_request(
    *,
    base_url: str,
    model: str,
    text: str,
    voice: str,
    instructions: str,
    language_type: str,
) -> tuple[str, dict]:
    endpoint = f"{base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"
    payload = {
        "model": model,
        "input": {
            "text": text,
        },
        "parameters": {
            "voice": voice,
            "language_type": language_type,
            "instructions": instructions,
        },
    }
    return endpoint, payload


def _hard_clamp(text: str, limit: int) -> str:
    text = text.strip()
    if not text:
        return ""
    if len(text) > limit:
        text = text[:limit]
    # 部分接口按 UTF-8 字节计
    encoded = text.encode("utf-8")
    byte_cap = min(limit * 3, API_HARD_MAX * 3)
    if len(encoded) > byte_cap:
        text = encoded[:byte_cap].decode("utf-8", errors="ignore").strip()
    return text[:limit]


def _truncate_at_boundary(text: str, limit: int) -> str:
    text = _hard_clamp(text, limit)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("。", "！", "？", "；", ".", "!", "?", ";", "，", ","):
        pos = cut.rfind(sep)
        if pos >= int(limit * 0.4):
            return _hard_clamp(cut[: pos + 1], limit)
    return _hard_clamp(cut, limit)


def split_tts_chunks(text: str, max_len: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    rest = text
    safety = 0
    while rest and safety < 32:
        safety += 1
        if len(rest) <= max_len:
            chunks.append(_hard_clamp(rest, max_len))
            break
        piece = _truncate_at_boundary(rest, max_len)
        if not piece:
            piece = _hard_clamp(rest, max_len)
        if not piece:
            break
        chunks.append(piece)
        rest = rest[len(piece) :].strip()
        if piece == rest:
            break

    return [c for c in chunks if c]


def estimate_playback_seconds(text: str, audio_segment_count: int = 1) -> float:
    chars = len(text)
    base = max(4.0, chars / 14.0)
    extra = max(0, audio_segment_count - 1) * 3.5
    return min(90.0, base + extra + 1.5)


async def _synthesize_chunk(text: str, profile: TTSProfile, settings) -> dict:
    runtime = load_runtime_settings()
    dashscope_key = runtime.api_keys.get("dashscope") or settings.dashscope_api_key
    limit = _effective_text_limit(profile)
    text = _hard_clamp(text, limit)
    if not text:
        raise TTSError("TTS chunk is empty after clamp")

    if len(text) > API_HARD_MAX or _estimate_tokens(text) > 520:
        text = _hard_clamp(text, TOKEN_SAFE_CHAR_CAP)
        if _estimate_tokens(text) > 480:
            text = text[:180]

    endpoint, payload = build_qwen_tts_request(
        base_url=settings.dashscope_base_url,
        model=settings.aliyun_tts_model,
        text=text,
        voice=profile.voice,
        instructions=profile.instructions,
        language_type=settings.aliyun_tts_language_type,
    )

    logger.debug("Qwen TTS request text_len=%s voice=%s", len(text), profile.voice)

    async with httpx.AsyncClient(timeout=TTS_HTTP_TIMEOUT) as client:
        response = await asyncio.wait_for(
            client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {dashscope_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ),
            timeout=TTS_CHUNK_DEADLINE_SEC,
        )

    if response.status_code >= 400:
        raise TTSError(
            f"HTTP {response.status_code} text_len={len(text)}: "
            f"{response.text[:320]}"
        )
    trace_id = str(uuid4())
    data = response.json()
    if data.get("code") and str(data.get("code")) not in {"0", "200"}:
        raise TTSError(f"Qwen TTS error {data.get('code')}: {data.get('message') or data.get('msg') or 'unknown'}")
    output = data.get("output") or {}
    audio = output.get("audio") or output.get("audio_url") or data.get("audio") or {}
    if isinstance(audio, str):
        data_url = audio
    else:
        data_url = audio.get("url") or audio.get("audio_url") or ""
        audio_b64 = audio.get("data") or audio.get("base64") or ""
        if not data_url and audio_b64:
            data_url = f"data:audio/mpeg;base64,{audio_b64}"
    if not data_url:
        raw = output.get("audio_data") or data.get("audio_data")
        if raw:
            data_url = f"data:audio/mpeg;base64,{raw}"
    if not data_url:
        raise TTSError("Qwen TTS did not return audio url or data")
    trace_id = data.get("request_id") or output.get("task_id") or trace_id
    return {
        "audio_url": data_url,
        "audio_id": trace_id,
        "expires_at": 0,
    }


def clamp_text_for_tts(text: str, max_chars: int = MAX_TTS_TOTAL_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return _truncate_at_boundary(text, max_chars)


async def synthesize_message_audio(
    message: DebateMessage,
    agent: AgentRole | None,
    *,
    on_chunk: Callable[[int, int], Awaitable[None] | None] | None = None,
) -> dict[str, object]:
    settings = get_settings()
    runtime = load_runtime_settings()
    if not settings.aliyun_tts_enabled:
        raise TTSError("TTS is disabled")
    if not (runtime.api_keys.get("dashscope") or settings.dashscope_api_key):
        raise TTSError("DASHSCOPE_API_KEY is not configured")

    profile = tts_profile_for_agent(agent)
    raw_text = markdown_to_speech_text(message.content)
    if not raw_text:
        raise TTSError("No speech text to synthesize")

    full_text = clamp_text_for_tts(raw_text)
    chunk_limit = _effective_text_limit(profile)
    chunks = split_tts_chunks(full_text, chunk_limit)[:MAX_TTS_CHUNKS]
    if not chunks:
        raise TTSError("No TTS chunks after split")

    audio_urls: list[str] = []
    expires_at = 0
    audio_id = ""
    total = len(chunks)

    for index, chunk in enumerate(chunks):
        if on_chunk is not None:
            maybe = on_chunk(index + 1, total)
            if asyncio.iscoroutine(maybe):
                await maybe
        try:
            part = await _synthesize_chunk(chunk, profile, settings)
        except (TTSError, asyncio.TimeoutError, httpx.HTTPError) as exc:
            if isinstance(exc, TTSError) and len(chunk) > 120:
                smaller = _hard_clamp(chunk, max(120, len(chunk) // 2))
                logger.warning("TTS retry chunk %s: %s -> %s chars", index, len(chunk), len(smaller))
                part = await _synthesize_chunk(smaller, profile, settings)
            else:
                if isinstance(exc, asyncio.TimeoutError):
                    raise TTSError(f"TTS 请求超时（第 {index + 1}/{total} 段）") from exc
                if isinstance(exc, httpx.HTTPError):
                    raise TTSError(f"TTS 网络错误（第 {index + 1}/{total} 段）: {exc}") from exc
                raise
        audio_urls.append(str(part["audio_url"]))
        expires_at = int(part.get("expires_at") or expires_at)
        audio_id = str(part.get("audio_id") or audio_id)

    return {
        "audio_url": audio_urls[0],
        "audio_urls": audio_urls,
        "audio_id": audio_id,
        "expires_at": expires_at,
        "voice": profile.voice,
        "instructions": profile.instructions,
        "tts_char_count": len(full_text),
        "tts_chunk_count": len(chunks),
        "playback_wait_sec": estimate_playback_seconds(full_text, len(chunks)),
        "truncated_for_tts": len(raw_text) > len(full_text),
    }
