from fastapi import APIRouter
from app.db import db
from app.models.academic import ExtractedTask
from app.services.sync_service import sync_service

router = APIRouter(prefix="/api/triage", tags=["Academic Triage"])

@router.get("", response_model=list[ExtractedTask])
async def get_triaged_tasks():
    """
    Returns triaged academic assignments and emails directly from the SQLite store.
    Instant read query (< 5ms) decoupled from LLM inference latency.
    """
    tasks = db.get_all_tasks()
    if not tasks and not db.get_all_opportunities():
        await sync_service.sync_all()
        tasks = db.get_all_tasks()
    return tasks
