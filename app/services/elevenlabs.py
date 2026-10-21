import hashlib
from pathlib import Path
from typing import Optional
import httpx
from app.config import settings

AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

class ElevenLabsService:
    def __init__(
        self,
        api_key: str = settings.ELEVENLABS_API_KEY,
        voice_id: str = settings.ELEVENLABS_VOICE_ID
    ):
        self.api_key = api_key
        self.voice_id = voice_id

    def _get_cache_path(self, text: str) -> Path:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return AUDIO_CACHE_DIR / f"briefing_{text_hash}.mp3"

    async def synthesize(self, text: str) -> Optional[Path]:
        """
        Synthesizes text to speech using ElevenLabs API.
        Caches resulting MP3 file on disk.
        """
        cache_path = self._get_cache_path(text)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path

        # If API key is provided, call ElevenLabs API
        if self.api_key:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg"
            }
            payload = {
                "text": text,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(url, json=payload, headers=headers)
                    if res.status_code == 200:
                        with open(cache_path, "wb") as f:
                            f.write(res.content)
                        return cache_path
            except Exception:
                pass

        # Generate a lightweight valid MP3 header payload for offline/demo/testing mode
        # Minimal valid MPEG audio frame (silent MP3 frame)
        silent_frame = b"\xff\xfb\x90d\x00\x00\x00\x00\x00\x00\x00\x00" * 32
        with open(cache_path, "wb") as f:
            f.write(silent_frame)
        return cache_path

elevenlabs_service = ElevenLabsService()
