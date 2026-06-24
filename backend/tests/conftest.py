"""集成测试：内存存储 + 禁用后台 auto_runner / 外部连接。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _reset_memory_store() -> None:
    from app.db import mongo
    from app.services import llm_usage

    mongo._memory_debates.clear()
    llm_usage._stats.clear()
    yield
    mongo._memory_debates.clear()
    llm_usage._stats.clear()


@pytest.fixture(autouse=True)
def _patch_background_services() -> None:
    with (
        patch("app.main.recover_auto_runners", new_callable=AsyncMock, return_value=0),
        patch("app.api.debates.start_auto"),
        patch("app.api.debates.resume_auto"),
        patch("app.api.debates.stop_auto"),
        patch("app.api.admin.resume_auto"),
        patch("app.api.admin.stop_auto"),
        patch("app.api.debates.append_changelog"),
        patch("app.api.debates.ensure_project_index"),
        patch("app.services.rag.init_vector_index"),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_argument_bank_title_llm() -> None:
    async def fake_title_summary(messages, **_kwargs):
        from app.services.argument_bank import short_argument_title

        prompt = messages[-1]["content"] if messages else ""
        match = re.search(r"论据：(\[[\s\S]*\])", prompt)
        rows = []
        if match:
            try:
                rows = json.loads(match.group(1))
            except json.JSONDecodeError:
                rows = []
        titles = [
            {
                "id": str(row.get("id") or ""),
                "title": short_argument_title(str(row.get("claim") or "")),
            }
            for row in rows
            if isinstance(row, dict)
        ]
        return json.dumps({"titles": titles}, ensure_ascii=False)

    with patch("app.services.argument_bank.chat_completion", side_effect=fake_title_summary):
        yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def mock_llm_stream() -> None:
    async def _fake_stream(*_args, **_kwargs):
        for chunk in ("**主席好**，", "这是集成测试发言。"):
            yield chunk

    with (
        patch(
            "app.workflow.debate_graph.chat_completion",
            new_callable=AsyncMock,
            return_value="内部草稿：争点与论据。",
        ),
        patch(
            "app.workflow.debate_graph.chat_completion_stream",
            side_effect=lambda *_a, **_k: _fake_stream(),
        ),
    ):
        yield
