from types import SimpleNamespace

import pytest

from app.models import DebateMessage, default_agents
from app.services.tts import build_qwen_tts_request, synthesize_message_audio


def test_build_qwen_tts_request_uses_dashscope_multimodal_generation_shape() -> None:
    url, payload = build_qwen_tts_request(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        model="qwen3-tts-instruct-flash",
        text="主席、各位评委，大家好。",
        voice="Cherry",
        instructions="正方一辩，快语速，吐字清晰。",
        language_type="Chinese",
    )

    assert url == "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    assert payload["model"] == "qwen3-tts-instruct-flash"
    assert payload["input"]["text"] == "主席、各位评委，大家好。"
    assert payload["parameters"]["voice"] == "Cherry"
    assert payload["parameters"]["language_type"] == "Chinese"
    assert payload["parameters"]["instructions"] == "正方一辩，快语速，吐字清晰。"


@pytest.mark.asyncio
async def test_long_debate_message_uses_one_short_tts_request(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_synthesize_chunk(text, *_args, **_kwargs):
        calls.append(text)
        return {
            "audio_url": "data:audio/mpeg;base64,ZmFrZQ==",
            "audio_id": "audio-1",
            "expires_at": 0,
        }

    monkeypatch.setattr(
        "app.services.tts.get_settings",
        lambda: SimpleNamespace(
            aliyun_tts_enabled=True,
            dashscope_api_key="test-key",
            dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            aliyun_tts_model="qwen3-tts-instruct-flash",
            aliyun_tts_language_type="Chinese",
        ),
    )
    monkeypatch.setattr(
        "app.services.tts.load_runtime_settings",
        lambda: SimpleNamespace(api_keys={}),
    )
    monkeypatch.setattr("app.services.tts._synthesize_chunk", fake_synthesize_chunk)

    message = DebateMessage(
        debate_id="debate-1",
        speaker_id="neg_1",
        speaker_name="橙律",
        side="negative",
        phase="opening_statement",
        segment_label="反方一辩立论",
        content="。".join(f"第{i}点，我们继续压缩核心论证，避免朗读完整长文" for i in range(80)),
    )

    result = await synthesize_message_audio(message, default_agents()[4])

    assert len(calls) == 1
    assert result["tts_chunk_count"] == 1
    assert len(calls[0]) <= 240
    assert result["truncated_for_tts"] is True
