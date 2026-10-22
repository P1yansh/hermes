import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "online"
        assert "Athena Hermes" in data["service"]
        assert "run_mode" in data
        assert "timezone" in data

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_sync_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/sync?force=true")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "synced"
        assert data["tasks_count"] > 0
        assert data["opportunities_count"] > 0

@pytest.mark.asyncio
async def test_triage_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/triage")
        assert res.status_code == 200
        tasks = res.json()
        assert isinstance(tasks, list)
        assert len(tasks) > 0

@pytest.mark.asyncio
async def test_scout_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/scout")
        assert res.status_code == 200
        data = res.json()
        assert "matches" in data
        assert len(data["matches"]) > 0

@pytest.mark.asyncio
async def test_radar_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/radar")
        assert res.status_code == 200
        data = res.json()
        assert "summary" in data
        assert "items" in data
        assert "watchlist" in data
        assert "watchlist_count" in data["summary"]
        assert data["summary"]["total_active"] > 0

@pytest.mark.asyncio
async def test_briefing_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/briefing")
        assert res.status_code == 200
        data = res.json()
        assert "script" in data
        assert "headline" in data

@pytest.mark.asyncio
async def test_briefing_audio_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/briefing/audio")
        assert res.status_code == 200
        assert res.headers["content-type"] == "audio/mpeg"
        assert len(res.content) > 0
