from httpx import AsyncClient


async def test_live(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.headers["x-request-id"]


async def test_ready_checks_dependencies(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"database": "ok", "redis": "ok"}


async def test_request_id_is_propagated(client: AsyncClient) -> None:
    resp = await client.get("/health/live", headers={"X-Request-ID": "abc123"})
    assert resp.headers["x-request-id"] == "abc123"
