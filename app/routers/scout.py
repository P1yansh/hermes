from fastapi import APIRouter
from app.agents.scout_agent import scout_agent
from app.models.opportunity import UserProfile, ScoutReport

router = APIRouter(prefix="/api/scout", tags=["Opportunity Scout"])

@router.get("", response_model=ScoutReport)
async def get_opportunities():
    """
    Returns active hackathons and internships matched to default developer profile.
    """
    return await scout_agent.scout()

@router.post("", response_model=ScoutReport)
async def post_custom_scout(profile: UserProfile):
    """
    Filters and ranks opportunities matched against custom skills and interests.
    """
    return await scout_agent.scout(profile=profile)
