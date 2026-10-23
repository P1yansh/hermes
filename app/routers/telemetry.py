from fastapi import APIRouter

from app.services.telemetry import get_gemma_telemetry

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


@router.get("/gemma")
async def gemma_telemetry(force: bool = False):
    """Return measured llama-server stats instead of hard-coded UI labels."""
    return await get_gemma_telemetry(force=force)
