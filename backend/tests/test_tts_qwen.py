from types import SimpleNamespace

import pytest

from app.models import DebateMessage, default_agents
from app.services.tts import (
    build_qwen_realtime_tts_url,
    build_qwen_realtime_session_update,
    build_qwen_tts_request,
    extract_realtime_audio_delta,
    synthesize_message_audio,
)


def test_build_qwen_realtime_tts_url_uses_api_ws_endpoint() -> None:
    url = build_qwen_realtime_tts_url(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        model="qwen3-tts-flash",
    )

    assert url == "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3-tts-flash-realtime"


def test_build_qwen_realtime_tts_url_preserves_workspace_host() -> None:
    url = build_qwen_realtime_tts_url(
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
        model="qwen3-tts-instruct-flash",
    )

    assert url == "wss://workspace.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen3-tts-instruct-flash-realtime"


def test_build_qwen_realtime_session_update_uses_pcm_for_streaming() -> None:
    payload = build_qwen_realtime_session_update(
        voice="Cherry",
        instructions="快语速，吐字清晰。",
        language_type="Chinese",
        model="qwen3-tts-instruct-flash-realtime",
    )

    assert payload["type"] == "session.update"
    assert payload["session"]["voice"] == "Cherry"
    assert payload["session"]["output_audio_format"] == "pcm"
    assert payload["session"]["language_type"] == "Chinese"
    assert payload["session"]["instructions"] == "快语速，吐字清晰。"


def test_extract_realtime_audio_delta_accepts_common_server_shapes() -> None:
    assert extract_realtime_audio_delta({"type": "response.audio.delta", "delta": "Zm9v"}) == "Zm9v"
    assert extract_realtime_audio_delta({"type": "response.audio.delta", "audio": {"data": "YmFy"}}) == "YmFy"
    assert extract_realtime_audio_delta({"type": "response.done"}) is None


def test_build_qwen_tts_request_uses_dashscope_multimodal_generation_shape() -> None:
    url, payload = build_qwen_tts_request(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        model="qwen3-tts-flash",
        text="主席、各位评委，大家好。",
        voice="Cherry",
        instructions="正方一辩，快语速，吐字清晰。",
        language_type="Chinese",
    )

    assert url == "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    assert payload["model"] == "qwen3-tts-flash"
    assert payload["input"]["text"] == "主席、各位评委，大家好。"
    assert payload["parameters"]["voice"] == "Cherry"
    assert payload["parameters"]["language_type"] == "Chinese"
    assert "instructions" not in payload["parameters"]


def test_build_qwen_tts_request_keeps_instructions_for_instruct_models() -> None:
    _url, payload = build_qwen_tts_request(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        model="qwen3-tts-instruct-flash",
        text="主席、各位评委，大家好。",
        voice="Cherry",
        instructions="正方一辩，快语速，吐字清晰。",
        language_type="Chinese",
    )

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
            aliyun_tts_model="qwen3-tts-flash",
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


@pytest.mark.asyncio
async def test_message_audio_prefers_realtime_websocket(monkeypatch) -> None:
    sent: list[dict] = []
    connected: list[tuple[str, dict]] = []

    class FakeWebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def send(self, payload: str) -> None:
            sent.append(__import__("json").loads(payload))

        def __aiter__(self):
            async def iterator():
                yield __import__("json").dumps({"type": "session.updated"})
                yield __import__("json").dumps({"type": "response.audio.delta", "delta": "AAECAw=="})
                yield __import__("json").dumps({"type": "response.done"})

            return iterator()

    def fake_connect(url, additional_headers=None, extra_headers=None, **_kwargs):
        connected.append((url, additional_headers or extra_headers or {}))
        return FakeWebSocket()

    monkeypatch.setattr(
        "app.services.tts.get_settings",
        lambda: SimpleNamespace(
            aliyun_tts_enabled=True,
            dashscope_api_key="test-key",
            dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            aliyun_tts_model="qwen3-tts-flash",
            aliyun_tts_language_type="Chinese",
        ),
    )
    monkeypatch.setattr(
        "app.services.tts.load_runtime_settings",
        lambda: SimpleNamespace(api_keys={}),
    )
    monkeypatch.setattr("app.services.tts._websocket_connect", fake_connect)

    message = DebateMessage(
        debate_id="debate-1",
        speaker_id="aff_1",
        speaker_name="云汐",
        side="affirmative",
        phase="opening_statement",
        segment_label="正方一辩立论",
        content="主席、各位评委，大家好。",
    )

    result = await synthesize_message_audio(message, default_agents()[0])

    assert connected[0][0].endswith("/api-ws/v1/realtime?model=qwen3-tts-flash-realtime")
    assert connected[0][1]["Authorization"] == "Bearer test-key"
    assert sent[0]["type"] == "session.update"
    assert sent[1]["type"] == "input_text_buffer.append"
    assert sent[2]["type"] == "input_text_buffer.commit"
    assert sent[3]["type"] == "session.finish"
    assert result["audio_url"].startswith("data:audio/wav;base64,")
    assert result["tts_backend"] == "dashscope_realtime"


@pytest.mark.asyncio
async def test_realtime_websocket_emits_audio_delta_callbacks(monkeypatch) -> None:
    deltas: list[tuple[int, str]] = []

    class FakeWebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def send(self, _payload: str) -> None:
            return None

        def __aiter__(self):
            async def iterator():
                yield __import__("json").dumps({"type": "response.audio.delta", "delta": "AAE="})
                yield __import__("json").dumps({"type": "response.audio.delta", "delta": "AgM="})
                yield __import__("json").dumps({"type": "response.done"})

            return iterator()

    monkeypatch.setattr(
        "app.services.tts.get_settings",
        lambda: SimpleNamespace(
            aliyun_tts_enabled=True,
            dashscope_api_key="test-key",
            dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
            aliyun_tts_model="qwen3-tts-flash",
            aliyun_tts_language_type="Chinese",
        ),
    )
    monkeypatch.setattr(
        "app.services.tts.load_runtime_settings",
        lambda: SimpleNamespace(api_keys={}),
    )
    monkeypatch.setattr("app.services.tts._websocket_connect", lambda *_args, **_kwargs: FakeWebSocket())

    message = DebateMessage(
        debate_id="debate-1",
        speaker_id="aff_1",
        speaker_name="云汐",
        side="affirmative",
        phase="opening_statement",
        segment_label="正方一辩立论",
        content="主席、各位评委，大家好。",
    )

    async def on_audio_delta(segment_index: int, audio_url: str) -> None:
        deltas.append((segment_index, audio_url))

    result = await synthesize_message_audio(message, default_agents()[0], on_audio_delta=on_audio_delta)

    assert [index for index, _url in deltas] == [1, 2]
    assert all(url.startswith("data:audio/wav;base64,") for _index, url in deltas)
    assert result["streamed_audio_delta_count"] == 2
