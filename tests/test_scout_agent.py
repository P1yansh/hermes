import pytest

from app.agents.scout_agent import OpportunityScoutAgent
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.models.opportunity import UserProfile

class _CountingConnector(BaseConnector):
    def __init__(self):
        self.mock = MockConnector()
        self.calls = 0

    async def get_recent_emails(self, max_results: int = 10):
        return await self.mock.get_recent_emails(max_results)

    async def get_classroom_courses(self):
        return await self.mock.get_classroom_courses()

    async def get_opportunities(self):
        self.calls += 1
        return await self.mock.get_opportunities()


@pytest.mark.asyncio
async def test_scout_polls_connector_on_every_incremental_sync():
    connector = _CountingConnector()
    agent = OpportunityScoutAgent(connector=connector)

    first = await agent.scout(force_refresh=False)
    second = await agent.scout(force_refresh=False)

    assert connector.calls == 2
    assert first.total_found == second.total_found
    assert second.total_found > 0


@pytest.mark.asyncio
async def test_scout_agent_default_profile():
    agent = OpportunityScoutAgent(connector=MockConnector())
    report = await agent.scout()
    assert report.total_found > 0
    assert len(report.matches) > 0
    # Top match should be highly relevant (e.g. Hacktoberfest or systems internship)
    assert report.matches[0].relevance_score >= 8

@pytest.mark.asyncio
async def test_scout_agent_case_insensitivity():
    agent = OpportunityScoutAgent(connector=MockConnector())
    # User skills with lowercase / mixed casing
    profile = UserProfile(skills=["python", "c++", "ai agents"])
    report = await agent.scout(profile=profile, force_refresh=True)
    assert report.total_found > 0
    # Hacktoberfest mentions Python and AI
    hacktoberfest = next((m for m in report.matches if "Hacktoberfest" in m.title), None)
    assert hacktoberfest is not None
    assert hacktoberfest.relevance_score >= 6

@pytest.mark.asyncio
async def test_scout_agent_empty_skills():
    agent = OpportunityScoutAgent(connector=MockConnector())
    # User with empty skill list
    profile = UserProfile(skills=[], min_prize_relevance=4)
    report = await agent.scout(profile=profile, force_refresh=True)
    assert report.total_found > 0
    # Fallback score should be assigned without throwing exceptions
    for m in report.matches:
        assert m.relevance_score >= 4

@pytest.mark.asyncio
async def test_scout_agent_high_threshold_filter():
    agent = OpportunityScoutAgent(connector=MockConnector())
    # Set an extreme threshold
    profile = UserProfile(skills=["Python"], min_prize_relevance=10)
    report = await agent.scout(profile=profile, force_refresh=True)
    # Only items with score 10 should remain
    for m in report.matches:
        assert m.relevance_score == 10
