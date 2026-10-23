from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.agents.triage_agent import AcademicTriageAgent
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.db import db
from app.models.academic import EmailMessage
from app.services.gemma_client import gemma_client

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

def test_tonight_relative_date_uses_ist():
    # 14:30 UTC is 20:00 IST. A naive UTC replace would produce 05:29 IST.
    email_dt = datetime(2026, 10, 23, 14, 30, tzinfo=timezone.utc)
    deadline = AcademicTriageAgent.resolve_relative_deadline("due tonight by 11:59 PM", email_dt)
    assert deadline is not None
    deadline_ist = deadline.astimezone(ZoneInfo("Asia/Kolkata"))
    assert (deadline_ist.year, deadline_ist.month, deadline_ist.day) == (2026, 10, 23)
    assert (deadline_ist.hour, deadline_ist.minute) == (23, 59)


def test_relative_date_treats_naive_anchor_as_user_timezone():
    # A naive anchor must be interpreted in USER_TIMEZONE, not the host's
    # local timezone, so the result does not change between CI and a laptop.
    naive_anchor = datetime(2026, 10, 23, 20, 0)
    deadline = AcademicTriageAgent.resolve_relative_deadline(
        "due tonight by 11:59 PM", naive_anchor
    )
    assert deadline is not None
    deadline_ist = deadline.astimezone(ZoneInfo("Asia/Kolkata"))
    assert (deadline_ist.day, deadline_ist.hour, deadline_ist.minute) == (23, 23, 59)


def test_tomorrow_relative_date_uses_ist():
    email_dt = datetime(2026, 10, 23, 14, 30, tzinfo=timezone.utc)
    deadline = AcademicTriageAgent.resolve_relative_deadline("tomorrow at 6 PM", email_dt)
    assert deadline is not None
    deadline_ist = deadline.astimezone(ZoneInfo("Asia/Kolkata"))
    assert (deadline_ist.year, deadline_ist.month, deadline_ist.day) == (2026, 10, 24)
    assert (deadline_ist.hour, deadline_ist.minute) == (18, 0)

    deadline_5pm = AcademicTriageAgent.resolve_relative_deadline("tomorrow at 5 PM", email_dt)
    assert deadline_5pm is not None
    assert deadline_5pm.astimezone(ZoneInfo("Asia/Kolkata")).hour == 17


@pytest.mark.asyncio
async def test_fallback_includes_deadline_text_key():
    extraction = await gemma_client.extract_email_task(
        sender="Prof. Turing <aturing@university.edu>",
        subject="CS401 Lab 3 due tonight",
        body="Submit the Raft implementation before 11:59 PM.",
    )
    assert extraction["category"] == "ACADEMIC_DEADLINE"
    assert extraction["deadline_text"] == "Tonight 11:59 PM"


class _CountingConnector(BaseConnector):
    def __init__(self):
        self.mock = MockConnector()
        self.email_calls = 0
        self.course_calls = 0

    async def get_recent_emails(self, max_results: int = 10):
        self.email_calls += 1
        return await self.mock.get_recent_emails(max_results)

    async def get_classroom_courses(self):
        self.course_calls += 1
        return await self.mock.get_classroom_courses()

    async def get_opportunities(self):
        return await self.mock.get_opportunities()


@pytest.mark.asyncio
async def test_triage_polls_connector_on_every_incremental_sync():
    connector = _CountingConnector()
    agent = AcademicTriageAgent(connector=connector)

    first = await agent.triage(force_refresh=False)
    second = await agent.triage(force_refresh=False)

    assert connector.email_calls == 2
    assert connector.course_calls == 2
    assert len(first) == len(second)
    assert len(second) == len(db.get_all_tasks())


def test_stage1_deterministic_filter():
    # 1. Informational & security alerts
    assert AcademicTriageAgent.classify_email_intent(
        sender="SerpApi <contact@serpapi.com>",
        subject="Welcome to SerpApi!",
        body="Welcome to SerpApi! Hi student, here is your API key..."
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
        sender="prof.menon@example.edu",
        subject="CS301 Lab 3 Raft Consensus Due Tomorrow",
        body="Please submit your homework assignment on Google Classroom."
    ) == "academic"
