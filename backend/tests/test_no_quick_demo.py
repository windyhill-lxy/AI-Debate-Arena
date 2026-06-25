import pytest
from httpx import AsyncClient

from app.services.schedule_config import list_schedule_templates


def test_schedule_templates_exclude_quick_demo() -> None:
    assert "quick_demo" not in list_schedule_templates()


@pytest.mark.asyncio
async def test_demo_endpoint_is_removed(client: AsyncClient) -> None:
    response = await client.post("/api/debates/demo")
    assert response.status_code == 404
