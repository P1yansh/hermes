import pytest
from app.connectors.mock_loader import MockConnector

@pytest.mark.asyncio
async def test_mock_loader_emails():
    connector = MockConnector()
    emails = await connector.get_recent_emails(max_results=5)
    assert len(emails) > 0
    assert any("CS401" in e.subject for e in emails)
    assert any(e.category == "spam_promo" for e in emails)

@pytest.mark.asyncio
async def test_mock_loader_classroom():
    connector = MockConnector()
    courses = await connector.get_classroom_courses()
    assert len(courses) > 0
    cs401 = next(c for c in courses if "CS401" in c.name)
    assert len(cs401.assignments) > 0
    assert any("Raft" in a.title for a in cs401.assignments)

@pytest.mark.asyncio
async def test_mock_loader_opportunities():
    connector = MockConnector()
    opps = await connector.get_opportunities()
    assert len(opps) > 0
    assert any("Hacktoberfest" in o.title for o in opps)
