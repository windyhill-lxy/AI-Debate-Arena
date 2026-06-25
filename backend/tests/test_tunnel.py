import pytest
from httpx import AsyncClient


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
