import hashlib
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from app.config import settings

AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

MIN_VALID_MP3_BYTES = 2048


def _is_valid_mp3(path: Path) -> bool:
    """Reject empty, truncated, and silent placeholder files."""
    try:
        if not path.exists() or path.stat().st_size < MIN_VALID_MP3_BYTES:
            return False
        with open(path, "rb") as f:
            header = f.read(4)
        return header[:3] == b"ID3" or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0)
    except OSError:
        return False


class ElevenLabsService:
    def __init__(
        self,
        api_key: str = settings.ELEVENLABS_API_KEY,
        voice_id: str = settings.ELEVENLABS_VOICE_ID
    ):
        self.api_key = api_key
        self.voice_id = voice_id

    def get_content_hash(self, text: str) -> str:
        """Deterministic content-addressable hash of voice ID + script text."""
        return hashlib.sha256(f"{self.voice_id}:{text.strip()}".encode("utf-8")).hexdigest()

    def get_cached_path(self, text: str) -> Optional[Path]:
        text_hash = self.get_content_hash(text)
        path = AUDIO_CACHE_DIR / f"briefing_{text_hash}.mp3"
        return path if _is_valid_mp3(path) else None

    def _write_atomic(self, cache_path: Path, content: bytes) -> Optional[Path]:
        """Write to a temp file, fsync, then replace the cache entry."""
        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                dir=str(AUDIO_CACHE_DIR), prefix=".briefing_", suffix=".tmp"
            )
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, cache_path)
            return cache_path
        except OSError:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            return None

    async def synthesize(self, text: str) -> Optional[Path]:
        """Synthesize text with ElevenLabs, or return None so the UI can fall back.

        A 384-byte silent MPEG frame used to be cached on every failure. That
        poisoned the content hash permanently: later successful calls saw a
        "cache hit" and played silence. Failures now leave no cache entry.
        """
        cache_path = AUDIO_CACHE_DIR / f"briefing_{self.get_content_hash(text)}.mp3"
        if _is_valid_mp3(cache_path):
            return cache_path

        if not self.api_key:
            return None

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
                if res.status_code != 200:
                    return None
                content = res.content
                if len(content) < MIN_VALID_MP3_BYTES:
                    return None
                if not (content[:3] == b"ID3" or (content[0] == 0xFF and (content[1] & 0xE0) == 0xE0)):
                    return None
                return self._write_atomic(cache_path, content)
        except Exception:
            return None


elevenlabs_service = ElevenLabsService()
