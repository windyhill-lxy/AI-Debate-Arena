import pytest

from app.services.llm_usage import get_debate_llm_stats, record_llm_call


@pytest.mark.asyncio
async def test_llm_usage_aggregates_per_debate() -> None:
    did = "debate-usage-1"
    await record_llm_call(
        did,
        operation="reflection_draft",
        model="m1",
        duration_ms=12.0,
        prompt_tokens=10,
        completion_tokens=20,
        ok=True,
    )
    await record_llm_call(
        did,
        operation="speech_stream",
        model="m1",
        duration_ms=30.0,
        prompt_tokens=0,
        completion_tokens=50,
        ok=True,
    )
    snap = await get_debate_llm_stats(did)
    assert snap["total_calls"] == 2
    assert snap["prompt_tokens"] == 10
    assert snap["completion_tokens"] == 70
    assert snap["operations"]["reflection_draft"] == 1
