"""Playwright E2E：依赖已启动的前端(5173)与后端(9000)。"""

from __future__ import annotations

import os

import pytest

FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
API_URL = os.environ.get("E2E_API_URL", "http://127.0.0.1:9000").rstrip("/")


@pytest.fixture(scope="session")
def browser_context_args() -> dict:
    return {"locale": "zh-CN"}


@pytest.fixture(scope="session")
def base_url() -> str:
    return FRONTEND_URL


@pytest.fixture(scope="session", autouse=True)
def _check_backend_up() -> None:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{API_URL}/health", timeout=5) as resp:
            if resp.status != 200:
                pytest.skip(f"后端未就绪: {API_URL}/health")
    except Exception as exc:
        pytest.skip(f"后端未启动 ({API_URL}): {exc}")
