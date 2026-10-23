import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, _SuppressLocalProbeAccessLog
from app.services import elevenlabs

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


def _access_record(method, path, status, client="127.0.0.1:12345"):
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        (client, method, path, "1.1", status),
        None,
    )


def test_local_probe_access_log_is_suppressed():
    log_filter = _SuppressLocalProbeAccessLog()

    assert not log_filter.filter(_access_record("GET", "/v1/models", 404))
    assert not log_filter.filter(_access_record("GET", "/v1/models?probe=1", 404))
    assert not log_filter.filter(_access_record("GET", "/health", 200))

    assert log_filter.filter(_access_record("GET", "/v1/models", 200))
    assert log_filter.filter(_access_record("GET", "/health", 500))
    assert log_filter.filter(_access_record("POST", "/v1/models", 404))
    assert log_filter.filter(_access_record("GET", "/api/health", 200))
    assert log_filter.filter(_access_record("GET", "/v1/models", 404, client="10.0.0.5:12345"))

    access_logger = logging.getLogger("uvicorn.access")
    assert any(isinstance(existing, _SuppressLocalProbeAccessLog) for existing in access_logger.filters)

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
async def test_briefing_audio_cache_hit():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        briefing_res = await client.get("/api/briefing")
        assert briefing_res.status_code == 200
        script = briefing_res.json()["script"]
        expected_hash = elevenlabs.elevenlabs_service.get_content_hash(script)
        assert briefing_res.json()["audio_hash"] == expected_hash

        cache_path = elevenlabs.AUDIO_CACHE_DIR / f"briefing_{expected_hash}.mp3"
        cache_path.write_bytes(b"ID3" + b"\x00" * 4096)

        res = await client.get("/api/briefing/audio")
        assert res.status_code == 200
        assert res.headers["content-type"] == "audio/mpeg"
        assert len(res.content) > 0


@pytest.mark.asyncio
async def test_briefing_audio_unavailable_returns_503():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/briefing")
        res = await client.get("/api/briefing/audio")
        assert res.status_code == 503
        assert "browser speech" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_telemetry_endpoint(monkeypatch):
    async def fake_telemetry(force: bool = False):
        return {
            "status": "online",
            "model": "gemma-3-4b-it",
            "tokens_per_second": 48.2,
            "model_size_gb": 2.48,
        }

    monkeypatch.setattr("app.routers.telemetry.get_gemma_telemetry", fake_telemetry)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/telemetry/gemma")
        assert res.status_code == 200
        assert res.json()["tokens_per_second"] == 48.2
