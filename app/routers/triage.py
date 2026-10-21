from fastapi import APIRouter
from app.agents.triage_agent import triage_agent
from app.models.academic import ExtractedTask

router = APIRouter(prefix="/api/triage", tags=["Academic Triage"])

@router.get("", response_model=list[ExtractedTask])
async def get_triaged_tasks():
    """
    Ingests recent student emails and Google Classroom assignments,
    filters noise/spam via Gemma 2, and returns structured tasks.
    """
    return await triage_agent.triage()
