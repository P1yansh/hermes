from fastapi import APIRouter
from app.db import db
from app.models.radar import RadarReport
from app.services.radar_engine import radar_engine
from app.services.sync_service import sync_service

router = APIRouter(prefix="/api/radar", tags=["Urgency Radar"])

@router.get("", response_model=RadarReport)
async def get_urgency_radar():
    """
    Compiles Academic Triage assignments and Opportunity Scout closing dates
    from persistent SQLite state into unified chronological urgency bands:
    - 🔴 Panic: < 6 hours
    - 🟡 Imminent: 6 - 24 hours
    - 🟢 Upcoming: > 24 hours
    - 📋 Watchlist: Actionable items with unconfirmed cutoffs
    """
    tasks = db.get_all_tasks()
    opps = db.get_all_opportunities()

    if not tasks and not opps:
        await sync_service.sync_all()
        tasks = db.get_all_tasks()
        opps = db.get_all_opportunities()

    raw_items: list[dict] = []
    for t in tasks:
        raw_items.append({
            "id": f"academic_{t.source_id}",
            "kind": "academic_assignment",
            "title": t.title,
            "source": t.course_or_sender,
            "deadline": t.deadline,
            "has_explicit_deadline": t.has_explicit_deadline,
            "action_url": t.submission_url,
            "account_source": t.account_source,
            "note": t.action_required
        })

    for o in opps:
        if not o.eligible:
            continue
        raw_items.append({
            "id": f"opp_{o.id}",
            "kind": "hackathon_deadline",
            "title": f"Registration: {o.title}",
            "source": o.organizer,
            "deadline": o.deadline,
            "has_explicit_deadline": o.has_explicit_deadline,
            "action_url": o.url,
            "account_source": o.source_inbox,
            "note": f"{o.type.capitalize()} • {o.eligibility_reason or o.mode or 'Online'}"
        })

    return radar_engine.compile_radar(raw_items)
