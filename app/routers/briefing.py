from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.routers.radar import get_urgency_radar
from app.agents.scout_agent import scout_agent
from app.models.radar import DailyBriefing
from app.services.briefing_engine import briefing_engine
from app.services.elevenlabs import elevenlabs_service

router = APIRouter(prefix="/api/briefing", tags=["Voice & Intelligence Briefing"])

@router.get("", response_model=DailyBriefing)
async def get_daily_briefing():
    """
    Compiles a spoken morning briefing from the Urgency Radar,
    synthesized into a conversational text script via Gemma 2.
    """
    radar = await get_urgency_radar()
    scout = await scout_agent.scout()
    top_opp = scout.matches[0].model_dump() if scout.matches else None

    briefing = await briefing_engine.build_briefing(radar, top_opportunity=top_opp)
    briefing.audio_available = True
    briefing.audio_url = "/api/briefing/audio"
    return briefing

@router.get("/audio")
async def get_briefing_audio():
    """
    Streams or downloads the high-fidelity ElevenLabs MP3 voice synthesis of the daily briefing.
    """
    briefing = await get_daily_briefing()
    audio_path = await elevenlabs_service.synthesize(briefing.script)
    if not audio_path or not audio_path.exists():
        raise HTTPException(status_code=500, detail="Audio synthesis failed")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename="hermes_morning_briefing.mp3"
    )
