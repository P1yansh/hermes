from fastapi import APIRouter
from app.services.sync_service import sync_service

router = APIRouter(prefix="/api/sync", tags=["Background Sync & Ingestion"])

@router.post("")
async def trigger_sync(force: bool = False):
    """
    Manually triggers an ingestion and triage sync:
    - Ingests unseen emails and classroom coursework.
    - Runs Stage-1 pre-filter and local Gemma 3 on new items.
    - Caches updated Radar and Briefing in SQLite.
    """
    return await sync_service.sync_all(force=force)
