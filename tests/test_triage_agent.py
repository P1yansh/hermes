import pytest
from app.agents.triage_agent import AcademicTriageAgent
from app.connectors.mock_loader import MockConnector
from app.db import Database

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

def test_stage1_deterministic_filter():
    # 1. Informational & security alerts
    assert AcademicTriageAgent.classify_email_intent(
        sender="SerpApi <contact@serpapi.com>",
        subject="Welcome to SerpApi!",
        body="Welcome to SerpApi! Hi Piyansh, here is your API key..."
    ) == "informational"

    assert AcademicTriageAgent.classify_email_intent(
        sender="Google <no-reply@accounts.google.com>",
        subject="Security alert",
        body="New passkey added to your account."
    ) == "informational"

    assert AcademicTriageAgent.classify_email_intent(
        sender="billing@service.com",
        subject="Receipt for your order #1234",
        body="Thank you for your payment confirmation."
    ) == "informational"

    # 2. Marketing / promotional spam
    assert AcademicTriageAgent.classify_email_intent(
        sender="store@campus.edu",
        subject="50% sale on hoodies",
        body="Buy university merchandise at a discount."
    ) == "spam"

    # 3. Opportunity alerts
    assert AcademicTriageAgent.classify_email_intent(
        sender="noreply@unstop.com",
        subject="Smart India Hackathon 2026 Registration Open",
        body="Compete for cash prizes in the national hackathon."
    ) == "opportunity"

    # 4. Academic deadlines
    assert AcademicTriageAgent.classify_email_intent(
        sender="prof.menon@iiitl.ac.in",
        subject="CS301 Lab 3 Raft Consensus Due Tomorrow",
        body="Please submit your homework assignment on Google Classroom."
    ) == "academic"
