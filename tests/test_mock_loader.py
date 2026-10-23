import json
from datetime import datetime, timezone

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
    hacktoberfest = next(o for o in opps if "Hacktoberfest" in o.title)
    assert hacktoberfest.deadline == datetime(2026, 10, 26, 6, 59, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_mock_loader_does_not_invent_missing_or_invalid_deadlines(tmp_path):
    (tmp_path / "mock_classroom.json").write_text(json.dumps([{
        "course_id": "course_x",
        "course_name": "CS999: Open-Ended Project",
        "assignments": [
            {
                "id": "cw_missing",
                "title": "Final Project",
                "description": "Schedule to be announced.",
            },
            {
                "id": "cw_invalid",
                "title": "Final Report",
                "description": "The fixture has a malformed date.",
                "due_hours_from_now": "soon",
            },
        ],
    }]), encoding="utf-8")
    (tmp_path / "mock_opportunities.json").write_text(json.dumps([
        {
            "id": "opp_missing",
            "title": "Unscheduled Fellowship",
            "type": "grant",
            "organizer": "Example Foundation",
            "description": "Applications open soon.",
            "url": "https://example.com/fellowship",
        },
        {
            "id": "opp_invalid",
            "title": "Malformed Fellowship",
            "type": "grant",
            "organizer": "Example Foundation",
            "description": "The fixture has a malformed date.",
            "url": "https://example.com/fellowship",
            "deadline_hours_from_now": "soon",
        },
        {
            "id": "opp_invalid_explicit",
            "title": "Explicitly Malformed Fellowship",
            "type": "grant",
            "organizer": "Example Foundation",
            "description": "The explicit date is malformed and must not fall back.",
            "url": "https://example.com/fellowship",
            "deadline": "not-a-date",
            "deadline_hours_from_now": 24,
        },
    ]), encoding="utf-8")

    connector = MockConnector(data_dir=tmp_path)
    courses = await connector.get_classroom_courses()
    opps = await connector.get_opportunities()

    assert all(a.due_at is None for a in courses[0].assignments)
    assert all(o.deadline is None for o in opps)
    assert all(o.has_explicit_deadline is False for o in opps)
