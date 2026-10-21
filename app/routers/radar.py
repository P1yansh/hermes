from fastapi import APIRouter
from app.agents.triage_agent import triage_agent
from app.agents.scout_agent import scout_agent
from app.models.radar import RadarReport
from app.services.radar_engine import radar_engine

router = APIRouter(prefix="/api/radar", tags=["Urgency Radar"])

@router.get("", response_model=RadarReport)
async def get_urgency_radar():
    """
    Compiles Academic Triage assignments and Opportunity Scout closing dates
    into unified chronological urgency bands:
    - 🔴 Panic: < 24 hours
    - 🟡 Imminent: 24 - 72 hours
    - 🟢 Upcoming: > 72 hours
    """
    tasks = await triage_agent.triage()
    scout_report = await scout_agent.scout()

    raw_items: list[dict] = []

    # Map academic tasks
    for t in tasks:
        if t.deadline:
            raw_items.append({
                "id": f"academic_{t.source_id}",
                "kind": "academic_assignment",
                "title": t.title,
                "source": t.course_or_sender,
                "deadline": t.deadline,
                "action_url": t.submission_url
            })

    # Map opportunity deadlines
    for o in scout_report.matches:
        raw_items.append({
            "id": f"opp_{o.id}",
            "kind": "hackathon_deadline",
            "title": f"Registration: {o.title}",
            "source": o.organizer,
            "deadline": o.deadline,
            "action_url": o.url
        })

    return radar_engine.compile_radar(raw_items)
