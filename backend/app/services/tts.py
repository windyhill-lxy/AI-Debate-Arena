import asyncio
import base64
import json
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
try:
    import websockets
except ImportError:  # pragma: no cover - exercised by fallback behavior in deployments
    websockets = None

from app.core.config import get_settings
from app.models import AgentRole, DebateMessage
from app.services.runtime_settings import load_runtime_settings

logger = logging.getLogger(__name__)

# 阿里云 Qwen3-TTS-Instruct：接口报错写 600，实际更接近 512 token；中文按保守估算
API_HARD_MAX = 600
TOKEN_SAFE_CHAR_CAP = 240  # 约 240 汉字 ≈ 480 token，低于 512 上限

DEBATE_SPEED_HINT = "快语速，辩论现场女声，吐字清晰。"

# 辩论现场只朗读核心摘要，避免一条发言拆成多段外部请求导致界面长时间卡在「合成中」。
MAX_TTS_TOTAL_CHARS = 220
MAX_TTS_CHUNKS = 1
TTS_HTTP_TIMEOUT = httpx.Timeout(connect=6.0, read=28.0, write=8.0, pool=6.0)
TTS_CHUNK_DEADLINE_SEC = 32.0
TTS_REALTIME_DEADLINE_SEC = 18.0
TTS_REALTIME_SAMPLE_RATE = 24000


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
    parameters = {
        "voice": voice,
        "language_type": language_type,
    }
    if "instruct" in model.lower() and instructions:
        parameters["instructions"] = instructions
    payload = {
        "model": model,
        "input": {
            "text": text,
        },
        "parameters": parameters,
    }
    return endpoint, payload


def _realtime_model_name(model: str) -> str:
    if model.endswith("-realtime"):
        return model
    if model.startswith("qwen3-tts-") and model.endswith("-flash"):
        return f"{model}-realtime"
    if model.startswith("qwen3-tts-") and "-realtime-" not in model:
        return model.replace("-202", "-realtime-202", 1)
    return "qwen3-tts-flash-realtime"


def build_qwen_realtime_tts_url(*, base_url: str, model: str) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme in {"http", "https"} else parsed.scheme
    path = parsed.path
    if "/api/" in path:
        path = path.split("/api/", 1)[0]
    path = f"{path.rstrip('/')}/api-ws/v1/realtime"
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["model"] = _realtime_model_name(model)
    return urlunsplit((scheme, parsed.netloc, path, urlencode(query_items), ""))


def build_qwen_realtime_session_update(
    *,
    voice: str,
    instructions: str,
    language_type: str,
    model: str,
) -> dict:
    session = {
        "voice": voice,
        "output_audio_format": "pcm",
        "language_type": language_type,
    }
    if "instruct" in model.lower() and instructions:
        session["instructions"] = instructions
    return {
        "type": "session.update",
        "session": session,
    }


def extract_realtime_audio_delta(event: dict) -> str | None:
    if event.get("type") != "response.audio.delta":
        return None
    delta = event.get("delta") or event.get("data")
    if isinstance(delta, str) and delta:
        return delta
    audio = event.get("audio")
    if isinstance(audio, dict):
        value = audio.get("data") or audio.get("base64") or audio.get("delta")
        if isinstance(value, str) and value:
            return value
    return None


def _websocket_connect(url: str, **kwargs):
    if websockets is None:
        raise TTSError("websockets dependency is not installed")
    return websockets.connect(url, **kwargs)


def _wav_data_url_from_pcm(pcm: bytes, *, sample_rate: int = TTS_REALTIME_SAMPLE_RATE) -> str:
    byte_rate = sample_rate * 2
    block_align = 2
    header = (
        b"RIFF"
        + (36 + len(pcm)).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + byte_rate.to_bytes(4, "little")
        + block_align.to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(pcm).to_bytes(4, "little")
    )
    return f"data:audio/wav;base64,{base64.b64encode(header + pcm).decode('ascii')}"


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


def _should_retry_shorter_chunk(exc: Exception, chunk: str) -> bool:
    if not isinstance(exc, TTSError) or len(chunk) <= 120:
        return False
    message = str(exc).lower()
    length_markers = (
        "too long",
        "length",
        "token",
        "maximum",
        "max",
        "600",
        "exceed",
        "超过",
        "过长",
    )
    return any(marker in message for marker in length_markers)


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


async def _synthesize_chunk_realtime(text: str, profile: TTSProfile, settings) -> dict:
    runtime = load_runtime_settings()
    dashscope_key = runtime.api_keys.get("dashscope") or settings.dashscope_api_key
    if not dashscope_key:
        raise TTSError("DASHSCOPE_API_KEY is not configured")
    model = _realtime_model_name(settings.aliyun_tts_model)
    url = build_qwen_realtime_tts_url(
        base_url=settings.dashscope_base_url,
        model=settings.aliyun_tts_model,
    )
    session_update = build_qwen_realtime_session_update(
        voice=profile.voice,
        instructions=profile.instructions,
        language_type=settings.aliyun_tts_language_type,
        model=model,
    )
    headers = {
        "Authorization": f"Bearer {dashscope_key}",
    }
    pcm_parts: list[bytes] = []
    trace_id = str(uuid4())

    async def run() -> None:
        try:
            connection = _websocket_connect(
                url,
                additional_headers=headers,
                ping_interval=20,
                close_timeout=5,
            )
        except TypeError:
            connection = _websocket_connect(
                url,
                extra_headers=headers,
                ping_interval=20,
                close_timeout=5,
            )
        async with connection as websocket:
            await websocket.send(json.dumps(session_update, ensure_ascii=False))
            await websocket.send(
                json.dumps(
                    {
                        "type": "input_text_buffer.append",
                        "text": text,
                    },
                    ensure_ascii=False,
                )
            )
            await websocket.send(json.dumps({"type": "input_text_buffer.commit"}, ensure_ascii=False))
            await websocket.send(json.dumps({"type": "session.finish"}, ensure_ascii=False))

            async for raw in websocket:
                if isinstance(raw, bytes):
                    pcm_parts.append(raw)
                    continue
                try:
                    event = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    continue
                trace = event.get("request_id") or event.get("event_id")
                if trace:
                    nonlocal_trace[0] = str(trace)
                if event.get("type") == "error" or event.get("error"):
                    error = event.get("error") or {}
                    message = error.get("message") if isinstance(error, dict) else str(error)
                    raise TTSError(message or "Qwen realtime TTS error")
                delta = extract_realtime_audio_delta(event)
                if delta:
                    pcm = base64.b64decode(delta)
                    pcm_parts.append(pcm)
                    continue
                if event.get("type") in {"response.done", "response.audio.done", "session.finished"}:
                    break

    nonlocal_trace = [trace_id]
    await asyncio.wait_for(run(), timeout=TTS_REALTIME_DEADLINE_SEC)
    if not pcm_parts:
        raise TTSError("Qwen realtime TTS did not return audio delta")
    return {
        "audio_url": _wav_data_url_from_pcm(b"".join(pcm_parts)),
        "audio_deltas": [_wav_data_url_from_pcm(part) for part in pcm_parts],
        "audio_id": nonlocal_trace[0],
        "expires_at": 0,
        "backend": "dashscope_realtime",
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
    on_audio_delta: Callable[[int, str], Awaitable[None] | None] | None = None,
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
    backend = "dashscope_http"
    streamed_audio_delta_count = 0

    for index, chunk in enumerate(chunks):
        if on_chunk is not None:
            maybe = on_chunk(index + 1, total)
            if asyncio.iscoroutine(maybe):
                await maybe
        try:
            try:
                part = await _synthesize_chunk_realtime(chunk, profile, settings)
            except Exception as realtime_exc:
                logger.warning("Realtime TTS fallback to HTTP for chunk %s: %s", index + 1, realtime_exc)
                part = await _synthesize_chunk(chunk, profile, settings)
        except (TTSError, asyncio.TimeoutError, httpx.HTTPError) as exc:
            if _should_retry_shorter_chunk(exc, chunk):
                smaller = _hard_clamp(chunk, max(120, len(chunk) // 2))
                logger.warning("TTS retry chunk %s: %s -> %s chars", index, len(chunk), len(smaller))
                try:
                    part = await _synthesize_chunk_realtime(smaller, profile, settings)
                except Exception:
                    part = await _synthesize_chunk(smaller, profile, settings)
            else:
                if isinstance(exc, asyncio.TimeoutError):
                    raise TTSError(f"TTS 请求超时（第 {index + 1}/{total} 段）") from exc
                if isinstance(exc, httpx.HTTPError):
                    raise TTSError(f"TTS 网络错误（第 {index + 1}/{total} 段）: {exc}") from exc
                raise
        audio_urls.append(str(part["audio_url"]))
        for audio_delta_url in part.get("audio_deltas", []) or []:
            streamed_audio_delta_count += 1
            if on_audio_delta is not None:
                maybe_delta = on_audio_delta(streamed_audio_delta_count, str(audio_delta_url))
                if asyncio.iscoroutine(maybe_delta):
                    await maybe_delta
        expires_at = int(part.get("expires_at") or expires_at)
        audio_id = str(part.get("audio_id") or audio_id)
        backend = str(part.get("backend") or "dashscope_http")

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
        "tts_backend": backend,
        "streamed_audio_delta_count": streamed_audio_delta_count,
    }
