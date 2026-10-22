import pytest
from app.agents.triage_agent import AcademicTriageAgent
from app.connectors.mock_loader import MockConnector

@pytest.mark.asyncio
async def test_triage_agent_execution():
    agent = AcademicTriageAgent(connector=MockConnector())
    tasks = await agent.triage(force_refresh=True)

    assert len(tasks) > 0
    # Check that classroom assignments were extracted
    assert any(t.source_type == "classroom" for t in tasks)
    # Check that actionable email was extracted and spam was filtered out
    assert any(t.source_type == "email" for t in tasks)
    # Confirm hoodie/merchandise spam email was NOT included as an actionable task
    assert not any("hoodies" in t.title.lower() for t in tasks)
