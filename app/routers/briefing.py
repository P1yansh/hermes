from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.db import db
from app.models.radar import DailyBriefing
from app.services.sync_service import sync_service
from app.services.elevenlabs import elevenlabs_service

router = APIRouter(prefix="/api/briefing", tags=["Voice & Intelligence Briefing"])

@router.get("", response_model=DailyBriefing)
async def get_daily_briefing():
    """
    Returns the cached morning briefing script generated from the active radar.
    """
    cached = db.get_latest_briefing()
    if not cached:
        await sync_service.sync_all()
        cached = db.get_latest_briefing()

    if not cached:
        raise HTTPException(status_code=500, detail="Failed to load daily briefing")

    return DailyBriefing(
        timestamp=datetime.fromisoformat(cached["created_at"]),
        headline=cached["headline"],
        script=cached["script"],
        audio_available=True,
        audio_url="/api/briefing/audio",
        items_covered=cached.get("items_covered", 0)
    )

@router.get("/audio")
async def get_briefing_audio():
    """
    Streams the high-fidelity ElevenLabs MP3 voice synthesis of the daily briefing.
    Uses content-addressable hash caching so identical scripts never re-hit external APIs.
    """
    briefing = await get_daily_briefing()
    
    # Check content-addressable cache first
    cached_path = elevenlabs_service.get_cached_path(briefing.script)
    if cached_path:
        return FileResponse(
            path=str(cached_path),
            media_type="audio/mpeg",
            filename="hermes_morning_briefing.mp3"
        )

    audio_path = await elevenlabs_service.synthesize(briefing.script)
    if not audio_path or not audio_path.exists():
        raise HTTPException(status_code=500, detail="Audio synthesis failed")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename="hermes_morning_briefing.mp3"
    )
