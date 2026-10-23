import pytest

from app.services import elevenlabs
from app.services.elevenlabs import ElevenLabsService


class _Response:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_elevenlabs_failure_writes_no_cache_file(monkeypatch):
    monkeypatch.setattr(elevenlabs.httpx, "AsyncClient", lambda *a, **k: _Client(error=RuntimeError("offline")))
    service = ElevenLabsService(api_key="test-key", voice_id="voice")

    result = await service.synthesize("briefing text")
    assert result is None
    assert list(elevenlabs.AUDIO_CACHE_DIR.iterdir()) == []


@pytest.mark.asyncio
async def test_elevenlabs_truncated_response_is_not_cached(monkeypatch):
    monkeypatch.setattr(
        elevenlabs.httpx,
        "AsyncClient",
        lambda *a, **k: _Client(response=_Response(200, b"\xff\xfb\x90d" + b"\x00" * 12)),
    )
    service = ElevenLabsService(api_key="test-key", voice_id="voice")

    result = await service.synthesize("briefing text")
    assert result is None
    assert list(elevenlabs.AUDIO_CACHE_DIR.iterdir()) == []


@pytest.mark.asyncio
async def test_elevenlabs_success_is_written_atomically(monkeypatch):
    calls = {"count": 0}

    def client_factory(*args, **kwargs):
        calls["count"] += 1
        return _Client(response=_Response(200, b"ID3" + b"\x00" * 4096))

    monkeypatch.setattr(elevenlabs.httpx, "AsyncClient", client_factory)
    service = ElevenLabsService(api_key="test-key", voice_id="voice")

    first = await service.synthesize("briefing text")
    second = await service.synthesize("briefing text")

    assert first is not None and first.exists()
    assert second == first
    assert calls["count"] == 1
    assert first.stat().st_size > 2048


def test_silent_placeholder_cache_file_is_ignored():
    service = ElevenLabsService(api_key="", voice_id="voice")
    text = "briefing text"
    poisoned = elevenlabs.AUDIO_CACHE_DIR / f"briefing_{service.get_content_hash(text)}.mp3"
    poisoned.write_bytes(b"\xff\xfb\x90d" + b"\x00" * 12)

    assert service.get_cached_path(text) is None
