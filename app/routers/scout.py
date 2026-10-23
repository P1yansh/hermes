from fastapi import APIRouter
from app.db import db
from app.models.opportunity import UserProfile, ScoutReport
from app.agents.scout_agent import scout_agent
from app.services.sync_service import sync_service

router = APIRouter(prefix="/api/scout", tags=["Opportunity Scout"])

@router.get("", response_model=ScoutReport)
async def get_opportunities():
    """
    Returns active hackathons and internships directly from the SQLite store.
    """
    opps = db.get_all_opportunities()
    if not opps and not db.get_all_tasks():
        await sync_service.sync_all()
        opps = db.get_all_opportunities()
    eligible = [o for o in opps if o.eligible]
    return ScoutReport(total_found=len(eligible), matches=eligible)

@router.post("", response_model=ScoutReport)
async def post_custom_scout(profile: UserProfile):
    """
    Filters and ranks opportunities matched against custom developer skills and priorities.
    """
    return await scout_agent.scout(profile=profile, force_refresh=False)
