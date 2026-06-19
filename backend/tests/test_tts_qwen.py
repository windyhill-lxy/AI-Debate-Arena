from app.services.tts import build_qwen_tts_request


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
