from app.config import settings
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.connectors.google_live import GoogleLiveConnector
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

    async def scout(self, profile: UserProfile | None = None) -> ScoutReport:
        if profile is None:
            profile = UserProfile()

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
            if relevance >= profile.min_prize_relevance:
                opp.relevance_score = relevance
                scored_matches.append(opp)

        # Sort matches by relevance score descending, then deadline ascending
        scored_matches.sort(key=lambda x: (-x.relevance_score, x.deadline))

        return ScoutReport(
            total_found=len(scored_matches),
            matches=scored_matches
        )

scout_agent = OpportunityScoutAgent()
