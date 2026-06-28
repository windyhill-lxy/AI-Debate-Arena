import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _isolate_tunnel_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEBATE_PROJECT_ROOT", str(tmp_path))
    from app.services import tunnel_service

    tunnel_service._runtime_proxy = None
    tunnel_service._active_provider = "ngrok"
    yield
    tunnel_service._runtime_proxy = None


@pytest.mark.asyncio
async def test_tunnel_status_endpoint(client: AsyncClient) -> None:
    res = await client.get("/api/tunnel/status")
    assert res.status_code == 200
    body = res.json()
    assert body["running"] is False
    assert body["provider"] in {"cloudflare-quick", "ngrok"}


@pytest.mark.asyncio
async def test_tunnel_stop_idempotent(client: AsyncClient) -> None:
    res = await client.post("/api/tunnel/stop")
    assert res.status_code == 200
    assert res.json()["running"] is False


@pytest.mark.asyncio
async def test_tunnel_diagnose_endpoint(client: AsyncClient) -> None:
    res = await client.get("/api/tunnel/diagnose")
    assert res.status_code == 200
    body = res.json()
    assert "checks" in body
    assert "suggestions" in body
    assert isinstance(body["checks"], list)


@pytest.mark.asyncio
async def test_tunnel_proxy_roundtrip(client: AsyncClient) -> None:
    res = await client.post("/api/tunnel/proxy", json={"proxy": "http://127.0.0.1:7890"})
    assert res.status_code == 200
    assert res.json()["proxy"] == "http://127.0.0.1:7890"
    res2 = await client.get("/api/tunnel/proxy")
    assert res2.json()["proxy"] == "http://127.0.0.1:7890"
    await client.post("/api/tunnel/proxy", json={"proxy": None})


@pytest.mark.asyncio
async def test_tunnel_provider_roundtrip(client: AsyncClient) -> None:
    res = await client.post("/api/tunnel/provider", json={"provider": "cloudflare"})
    assert res.status_code == 200
    assert res.json()["provider"] == "cloudflare"

    res2 = await client.get("/api/tunnel/providers")
    assert res2.status_code == 200
    assert res2.json()["current"] == "cloudflare"

    await client.post("/api/tunnel/provider", json={"provider": "auto"})


def test_auto_tunnel_start_reports_cloudflare_after_ngrok_fallback(monkeypatch) -> None:
    from app.services import tunnel_service

    monkeypatch.setattr(tunnel_service, "_origin_reachable", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(tunnel_service, "get_tunnel_provider", lambda: "auto")
    monkeypatch.setattr(tunnel_service.tunnel_ngrok, "get_ngrok_authtoken", lambda: "configured")
    monkeypatch.setattr(tunnel_service.tunnel_ngrok, "start", lambda *_args, **_kwargs: (None, "等待 ngrok 公网地址超时"))

    def fake_cloudflare(target: str):
        return tunnel_service.TunnelStatus(
            running=True,
            url="https://demo.trycloudflare.com",
            error=None,
            provider="cloudflare-quick",
            local_url=target,
            healthy=True,
        )

    monkeypatch.setattr(tunnel_service, "_start_cloudflare", fake_cloudflare)

    status = tunnel_service.start_tunnel("http://127.0.0.1:5173")

    assert status.running is True
    assert status.provider == "cloudflare-quick"
