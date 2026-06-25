import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from urllib import parse

import httpx

from app.core.config import get_settings
from app.services.runtime_settings import load_runtime_settings


ASR_TIMEOUT = httpx.Timeout(connect=8.0, read=45.0, write=20.0, pool=8.0)
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class ASRError(Exception):
    pass


@dataclass
class _CachedToken:
    value: str = ""
    expire_time: int = 0


_TOKEN = _CachedToken()


def _encode_text(text: str | bytes) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    encoded = parse.quote_plus(text)
    return encoded.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def _encode_dict(values: dict[str, str]) -> str:
    encoded = parse.urlencode([(key, values[key]) for key in sorted(values)])
    return encoded.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


async def _create_token() -> tuple[str, int]:
    settings = get_settings()
    runtime = load_runtime_settings()
    ak_id = runtime.api_keys.get("aliyun_ak_id") or settings.aliyun_ak_id
    ak_secret = runtime.api_keys.get("aliyun_ak_secret") or settings.aliyun_ak_secret
    if not ak_id or not ak_secret:
        raise ASRError("缺少 ALIYUN_AK_ID 或 ALIYUN_AK_SECRET")

    params = {
        "AccessKeyId": ak_id,
        "Action": "CreateToken",
        "Format": "JSON",
        "RegionId": settings.aliyun_asr_region,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2019-02-28",
    }
    query_string = _encode_dict(params)
    string_to_sign = f"GET&{_encode_text('/')}&{_encode_text(query_string)}"
    signature = base64.b64encode(
        hmac.new(
            f"{ak_secret}&".encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    )
    url = f"{settings.aliyun_token_endpoint}?Signature={_encode_text(signature)}&{query_string}"
    async with httpx.AsyncClient(timeout=ASR_TIMEOUT) as client:
        response = await client.get(url, headers={"Accept": "application/json"})
    if response.status_code >= 400:
        raise ASRError(f"获取阿里云 Token 失败：{response.text[:200]}")
    data = response.json()
    token = data.get("Token") or {}
    token_id = token.get("Id")
    expire_time = int(token.get("ExpireTime") or 0)
    if not token_id or not expire_time:
        raise ASRError(f"阿里云 Token 响应无效：{response.text[:200]}")
    return token_id, expire_time


async def _get_token() -> str:
    now = int(time.time())
    if _TOKEN.value and _TOKEN.expire_time - now > 300:
        return _TOKEN.value
    token, expire_time = await _create_token()
    _TOKEN.value = token
    _TOKEN.expire_time = expire_time
    return token


async def recognize_speech(audio: bytes, audio_format: str = "wav") -> dict[str, str | int]:
    settings = get_settings()
    runtime = load_runtime_settings()
    appkey = runtime.api_keys.get("aliyun_isi_appkey") or settings.aliyun_isi_appkey or settings.nls_app_key
    if not settings.aliyun_asr_enabled:
        raise ASRError("语音识别已关闭（ALIYUN_ASR_ENABLED=false）")
    if not appkey:
        raise ASRError("缺少 ALIYUN_ISI_APPKEY 或 NLS_APP_KEY")
    if not audio:
        raise ASRError("音频为空")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ASRError("音频过大，请控制在 60 秒以内")

    token = await _get_token()
    params = {
        "appkey": appkey,
        "format": audio_format,
        "sample_rate": str(settings.aliyun_asr_sample_rate),
        "enable_punctuation_prediction": "true",
        "enable_inverse_text_normalization": "true",
        "enable_voice_detection": "true",
    }
    url = f"{settings.aliyun_asr_endpoint}?{parse.urlencode(params)}"
    async with httpx.AsyncClient(timeout=ASR_TIMEOUT) as client:
        response = await client.post(
            url,
            content=audio,
            headers={
                "Content-Type": "application/octet-stream",
                "X-NLS-Token": token,
            },
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ASRError(f"阿里云识别响应不是 JSON：{response.text[:200]}") from exc

    status = int(data.get("status") or data.get("Status") or response.status_code)
    text = (data.get("result") or data.get("Result") or "").strip()
    if response.status_code >= 400 or status not in {20000000, 200}:
        message = data.get("message") or data.get("Message") or response.text[:200]
        raise ASRError(f"阿里云识别失败：{message}")
    if not text:
        raise ASRError("未识别到有效文字")
    return {"text": text, "status": status}
