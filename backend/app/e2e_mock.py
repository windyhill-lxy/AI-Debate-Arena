"""E2E 模式：无 API Key 时用 Mock LLM（设置环境变量 DEBATE_E2E_MOCK=1）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def apply_e2e_llm_patches() -> None:
    async def _fake_stream(*_args, **_kwargs):
        for chunk in ("**E2E测试**，", "首条流式发言已就绪。"):
            yield chunk

    patch(
        "app.workflow.debate_graph.chat_completion",
        new_callable=AsyncMock,
        return_value="E2E 内部草稿。",
    ).start()
    patch(
        "app.workflow.debate_graph.chat_completion_stream",
        side_effect=lambda *_a, **_k: _fake_stream(),
    ).start()
