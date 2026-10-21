from app.config import settings, to_utc
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.connectors.google_live import GoogleLiveConnector
from app.db import db
from app.models.opportunity import OpportunityItem, UserProfile, ScoutReport
from app.services.gemma_client import gemma_client

class OpportunityScoutAgent:
    def __init__(self, connector: BaseConnector | None = None):
        if connector:
            self.connector = connector
        elif settings.DATA_SOURCE == "live":
            self.connector = GoogleLiveConnector(
                credentials_path=settings.GOOGLE_CREDENTIALS_PATH,
                token_path=settings.GOOGLE_TOKEN_PATH
            )
        else:
            self.connector = MockConnector()

    async def scout(self, profile: UserProfile | None = None, force_refresh: bool = False) -> ScoutReport:
        if profile is None:
            profile = UserProfile()

        # If cache exists and no custom profile / force_refresh is requested, return stored opportunities
        if not force_refresh:
            cached_opps = db.get_all_opportunities()
            if cached_opps:
                # Filter by min_prize_relevance
                filtered = [o for o in cached_opps if o.relevance_score >= profile.min_prize_relevance]
                filtered.sort(key=lambda x: (-x.relevance_score, x.deadline))
                return ScoutReport(total_found=len(filtered), matches=filtered)

        raw_opportunities = await self.connector.get_opportunities()
        scored_matches: list[OpportunityItem] = []

        for opp in raw_opportunities:
            score_data = await gemma_client.score_opportunity(
                title=opp.title,
                description=opp.description,
                tags=opp.tags,
                user_skills=profile.skills
            )

            relevance = score_data.get("relevance_score", opp.relevance_score)
            opp.relevance_score = relevance
            opp.deadline = to_utc(opp.deadline)

            if relevance >= profile.min_prize_relevance:
                scored_matches.append(opp)

        # Save all scored opportunities to SQLite
        if scored_matches:
            db.save_opportunities(scored_matches)

        scored_matches.sort(key=lambda x: (-x.relevance_score, x.deadline))
        return ScoutReport(
            total_found=len(scored_matches),
            matches=scored_matches
        )

scout_agent = OpportunityScoutAgent()
