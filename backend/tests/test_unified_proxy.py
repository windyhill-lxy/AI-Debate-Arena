"""统一服务 WS 代理 smoke：Starlette app 直连后端。"""

from __future__ import annotations

import json
import threading
import time

import pytest
import uvicorn
from starlette.testclient import TestClient


def _run_backend(port: int) -> None:
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture(scope="module")
def unified_proxy_client():
    from pathlib import Path

    backend_port = 19001
    proxy_port = 15173
    backend_thread = threading.Thread(
        target=_run_backend,
        args=(backend_port,),
        daemon=True,
    )
    backend_thread.start()
    for _ in range(40):
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{backend_port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        pytest.skip("backend not ready for unified proxy test")

    import os

    os.environ["DEBATE_BACKEND_URL"] = f"http://127.0.0.1:{backend_port}"
    from scripts.serve_unified import make_app

    root = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not (root / "index.html").is_file():
        pytest.skip("frontend dist missing for unified proxy test")

    proxy_thread = threading.Thread(
        target=lambda: uvicorn.run(make_app(root), host="127.0.0.1", port=proxy_port, log_level="warning"),
        daemon=True,
    )
    proxy_thread.start()
    for _ in range(40):
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{proxy_port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        pytest.skip("unified proxy not ready")

    with TestClient(f"http://127.0.0.1:{proxy_port}") as client:
        yield client, backend_port


@pytest.mark.slow
def test_unified_proxy_ws_snapshot(unified_proxy_client) -> None:
    client, _backend_port = unified_proxy_client
    create = client.post(
        "/api/debates",
        json={"topic": "proxy ws", "mode": "ai_autonomous", "schedule_template": "formal_4v4"},
    )
    assert create.status_code == 200
    debate_id = create.json()["id"]

    with client.websocket_connect(f"/api/debates/ws/{debate_id}") as ws:
        msg = ws.receive_json()
    assert msg["event"] == "snapshot"
    assert msg["debate"]["id"] == debate_id
