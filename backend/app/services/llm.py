import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.llm_usage import record_llm_call
from app.services.runtime_settings import load_runtime_settings

logger = logging.getLogger(__name__)


class DeepSeekError(Exception):
    pass


def strip_model_reasoning(text: str) -> str:
    """Remove model-visible chain-of-thought tags before streaming or persisting output."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thinking>[\s\S]*?</thinking>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<reasoning>[\s\S]*?</reasoning>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*(思考过程|思考|推理过程|Reasoning)\s*[:：][\s\S]*?(?=\n\s*#{1,3}\s|\n\s*(质询|回应|一辩|二辩|三辩|四辩)[:：]|$)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_model_name(model_name: str | None) -> str:
    """
    将历史/别名模型名归一为当前供应商可接受的规范名。
    """
    raw = (model_name or "").strip()
    if not raw:
        return raw
    lower = raw.lower()
    alias = {
        # DeepSeek 新旧名兼容
        "deepseek-flash": "deepseek-v4-flash",
        "deepseek-chat": "deepseek-v4-pro",
        "deepseek-v3": "deepseek-v4-pro",
        # Kimi 常见别名
        "kimi": "moonshot-v1-8k",
        # MiniMax 常见别名（兼容老写法）
        "minimax-m1": "MiniMax-M2.1-highspeed",
        "abab6.5s-chat": "MiniMax-M2.1-highspeed",
        "abab5.5-chat": "MiniMax-M2.1-highspeed",
    }
    return alias.get(lower, raw)


def _split_agent_id(agent_id: str | None) -> tuple[str, int]:
    if not agent_id:
        return "", 0
    if agent_id == "judge":
        return "judge", 0
    match = re.fullmatch(r"(aff|neg)_(\d)", agent_id)
    if not match:
        return "", 0
    side = "affirmative" if match.group(1) == "aff" else "negative"
    return side, int(match.group(2))


def _model_for_agent(*, side: str, position: int, settings) -> tuple[str | None, str]:
    runtime = load_runtime_settings()
    prefix = "aff" if side == "affirmative" else "neg" if side == "negative" else side
    agent_id = "judge" if side == "judge" else f"{prefix}_{position}" if prefix in {"aff", "neg"} else ""
    model = runtime.models.get(agent_id) or settings.deepseek_flash_model or settings.deepseek_model
    return runtime.api_keys.get("deepseek") or settings.deepseek_api_key, model


def _candidate_models(explicit: str | None) -> list[str]:
    """主模型 + 配置中的备用模型列表 + 通用兜底（多模型降级）。"""
    settings = get_settings()
    runtime = load_runtime_settings()
    if explicit:
        return [_normalize_model_name(explicit)]
    extras = [m.strip() for m in (settings.deepseek_fallback_models or "").split(",") if m.strip()]
    ordered: list[str] = []
    for m in [
        explicit,
        runtime.defaults.get("default_model"),
        settings.deepseek_flash_model,
        settings.deepseek_model,
        *extras,
        "deepseek-v4-pro",
    ]:
        if m:
            normalized = _normalize_model_name(m)
            if normalized and normalized not in ordered:
                ordered.append(normalized)
    return ordered


def _auto_search_enabled() -> bool:
    settings = get_settings()
    return bool(settings.deepseek_auto_search or "dsapi" in settings.deepseek_base_url.lower())


def _with_auto_search(payload: dict[str, Any]) -> dict[str, Any]:
    if not _auto_search_enabled():
        return payload
    return {
        **payload,
        "enable_search": True,
        "search": True,
    }


def resolve_model(*, phase: str, speaker_id: str | None = None) -> str:
    settings = get_settings()
    side, position = _split_agent_id(speaker_id)
    if side == "judge" or position in {1, 2, 3, 4}:
        _, model = _model_for_agent(side=side, position=position, settings=settings)
        if model:
            return _normalize_model_name(model)
    pro_phases = {p.strip() for p in settings.deepseek_pro_phases.split(",") if p.strip()}
    if phase in pro_phases and settings.deepseek_model:
        return _normalize_model_name(settings.deepseek_model)
    return _normalize_model_name(settings.deepseek_flash_model or settings.deepseek_model)


def _provider_for_model(model_name: str, settings) -> str:
    lower = (model_name or "").lower()
    if lower.startswith("qwen") or lower.startswith("qwq"):
        return "qwen"
    if lower.startswith("moonshot") or "kimi" in lower:
        return "kimi"
    if lower.startswith("minimax") or lower.startswith("abab") or lower.startswith("m1"):
        return "minimax"
    return "deepseek"


def _endpoint_and_headers(provider: str, settings) -> tuple[str, dict[str, str], bool]:
    runtime = load_runtime_settings()
    api_keys = runtime.api_keys
    defaults = runtime.defaults
    if provider == "qwen":
        api_key = api_keys.get("qwen") or settings.qwen_api_key
        if not api_key:
            raise DeepSeekError("QWEN_API_KEY is not configured")
        return (
            f"{(defaults.get('qwen_base_url') or settings.qwen_base_url).rstrip('/')}/chat/completions",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            False,
        )
    if provider == "kimi":
        api_key = api_keys.get("kimi") or settings.kimi_api_key_effective
        if not api_key:
            raise DeepSeekError("KIMI_API_KEY is not configured")
        return (
            f"{(defaults.get('kimi_base_url') or settings.kimi_base_url).rstrip('/')}/chat/completions",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            False,
        )
    if provider == "minimax":
        api_key = api_keys.get("minimax") or settings.minimax_api_key_effective
        if not api_key:
            raise DeepSeekError("MINIMAX_API_KEY is not configured")
        return (
            f"{(defaults.get('minimax_base_url') or settings.minimax_base_url).rstrip('/')}/chat/completions",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            False,
        )
    deepseek_key = api_keys.get("deepseek") or settings.deepseek_api_key
    if not deepseek_key:
        raise DeepSeekError("DEEPSEEK_API_KEY is not configured")
    return (
        f"{(defaults.get('deepseek_base_url') or settings.deepseek_base_url).rstrip('/')}/chat/completions",
        {
            "Authorization": f"Bearer {deepseek_key}",
            "Content-Type": "application/json",
        },
        True,
    )


def _provider_payload(provider: str, payload: dict[str, Any], *, settings) -> dict[str, Any]:
    if provider == "minimax":
        minimax_payload = {
            "model": payload["model"],
            "messages": payload["messages"],
            "temperature": payload.get("temperature", 0.7),
            "max_tokens": payload.get("max_tokens", 1400),
            "stream": bool(payload.get("stream", False)),
        }
        return minimax_payload
    if provider == "deepseek":
        return _with_auto_search(payload)
    return payload


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1400,
    debate_id: str | None = None,
    operation: str = "chat_completion",
) -> str:
    # 统一走 DeepSeek 官方流式接口（stream=true），再在服务端聚合为完整文本返回。
    chunks: list[str] = []
    async for chunk in chat_completion_stream(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        debate_id=debate_id,
        operation=operation,
    ):
        if chunk:
            chunks.append(chunk)
    content = "".join(chunks).strip()
    content = strip_model_reasoning(content)
    if not content:
        raise DeepSeekError("DeepSeek stream returned empty content")
    return content


async def chat_completion_stream(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1400,
    debate_id: str | None = None,
    operation: str = "chat_completion_stream",
) -> AsyncIterator[str]:
    settings = get_settings()

    models_to_try = _candidate_models(model)
    last_error = ""
    t0 = time.perf_counter()
    used_model = models_to_try[0] if models_to_try else "unknown"
    last_pt = 0
    last_ct = 0

    async with httpx.AsyncClient(timeout=90.0) as client:
        for model_name in models_to_try:
            used_model = model_name
            provider = _provider_for_model(model_name, settings)
            payload: dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            try:
                url, headers, allow_auto_search = _endpoint_and_headers(provider, settings)
            except DeepSeekError as exc:
                last_error = str(exc)
                continue
            request_json = _provider_payload(provider, payload, settings=settings)
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=request_json,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    last_error = body.decode()[:300]
                    if response.status_code in {400, 422} and allow_auto_search and _auto_search_enabled():
                        async with client.stream("POST", url, headers=headers, json=payload) as retry:
                            if retry.status_code < 400:
                                response = retry
                                async for line in response.aiter_lines():
                                    if not line.startswith("data: "):
                                        continue
                                    data = line[6:].strip()
                                    if data == "[DONE]":
                                        break
                                    try:
                                        chunk = json.loads(data)
                                        usage = chunk.get("usage")
                                        if usage:
                                            last_pt = int(usage.get("prompt_tokens") or last_pt)
                                            last_ct = int(usage.get("completion_tokens") or last_ct)
                                        delta = chunk["choices"][0].get("delta", {})
                                        text = delta.get("content") or ""
                                        if text:
                                            yield text
                                    except (json.JSONDecodeError, KeyError, IndexError):
                                        continue
                                elapsed_ms = (time.perf_counter() - t0) * 1000
                                await record_llm_call(
                                    debate_id,
                                    operation=operation,
                                    model=model_name,
                                    duration_ms=elapsed_ms,
                                    prompt_tokens=last_pt,
                                    completion_tokens=last_ct,
                                    ok=True,
                                )
                                return
                            retry_body = await retry.aread()
                            last_error = retry_body.decode()[:300]
                    if response.status_code not in {400, 404, 422}:
                        break
                    continue

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        usage = chunk.get("usage")
                        if usage:
                            last_pt = int(usage.get("prompt_tokens") or last_pt)
                            last_ct = int(usage.get("completion_tokens") or last_ct)
                        delta = chunk["choices"][0].get("delta", {})
                        text = delta.get("content") or ""
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "llm stream_end op=%s model=%s debate_id=%s ms=%.1f prompt_tokens=%d completion_tokens=%d",
                    operation,
                    model_name,
                    debate_id or "-",
                    elapsed_ms,
                    last_pt,
                    last_ct,
                )
                await record_llm_call(
                    debate_id,
                    operation=operation,
                    model=model_name,
                    duration_ms=elapsed_ms,
                    prompt_tokens=last_pt,
                    completion_tokens=last_ct,
                    ok=True,
                )
                return

    elapsed_ms = (time.perf_counter() - t0) * 1000
    await record_llm_call(
        debate_id,
        operation=f"{operation}:error",
        model=used_model,
        duration_ms=elapsed_ms,
        prompt_tokens=0,
        completion_tokens=0,
        ok=False,
    )
    raise DeepSeekError(f"DeepSeek API error: {last_error}")


def extract_json_block(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise


def format_history(messages: list[Any], limit: int = 8) -> str:
    """兼容旧调用：默认只输出双方公开发言，不包含队内讨论。"""
    from app.models import DebateMessage
    from app.services.message_visibility import format_debate_history

    parsed: list[DebateMessage] = []
    for message in messages:
        if isinstance(message, DebateMessage):
            parsed.append(message)
        else:
            parsed.append(
                DebateMessage(
                    debate_id=message.get("debate_id", ""),
                    speaker_id=message.get("speaker_id", ""),
                    speaker_name=message.get("speaker_name", "未知"),
                    side=message.get("side", ""),
                    content=message.get("content", ""),
                    phase=message.get("phase", ""),
                    segment_label=message.get("segment_label"),
                )
            )
    return format_debate_history(parsed, viewer_side="judge", in_internal_phase=False, limit=limit)
