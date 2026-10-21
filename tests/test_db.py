import pytest
from datetime import datetime, timezone, timedelta
from app.db import Database
from app.models.academic import ExtractedTask
from app.models.opportunity import OpportunityItem

@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_hermes.db"
    database = Database(db_path=str(db_file))
    database.init_db()
    return database

def test_db_init_and_seen_items(test_db):
    assert not test_db.is_item_seen("msg_123")
    test_db.mark_item_seen("msg_123", "email")
    assert test_db.is_item_seen("msg_123")

def test_db_tasks_crud(test_db):
    task = ExtractedTask(
        source_type="classroom",
        source_id="cw_999",
        course_or_sender="CS401",
        title="Raft Test",
        deadline=datetime.now(timezone.utc) + timedelta(hours=5),
        action_required="Submit lab",
        is_urgent=True,
        submission_url="https://classroom.google.com/test",
        estimated_hours=2.0,
        confidence=1.0
    )
    test_db.save_tasks([task])
    assert test_db.is_item_seen("cw_999")

    tasks = test_db.get_all_tasks()
    assert len(tasks) == 1
    assert tasks[0].source_id == "cw_999"
    assert tasks[0].course_or_sender == "CS401"
    assert tasks[0].is_urgent is True

def test_db_opportunities_crud(test_db):
    opp = OpportunityItem(
        id="opp_test_1",
        title="AI Hackathon",
        type="hackathon",
        organizer="DEV",
        deadline=datetime.now(timezone.utc) + timedelta(days=3),
        prizes="$2000",
        tags=["python", "ai"],
        description="Build something cool",
        url="https://example.com",
        relevance_score=9
    )
    test_db.save_opportunities([opp])
    assert test_db.is_item_seen("opp_test_1")

    opps = test_db.get_all_opportunities()
    assert len(opps) == 1
    assert opps[0].title == "AI Hackathon"
    assert opps[0].tags == ["python", "ai"]

def test_db_briefing_cache(test_db):
    assert test_db.get_latest_briefing() is None
    test_db.save_briefing(
        headline="1 Deadline Due",
        script="Good morning briefing",
        audio_hash="abc123hash",
        items_covered=1
    )
    b = test_db.get_latest_briefing()
    assert b is not None
    assert b["headline"] == "1 Deadline Due"
    assert b["audio_hash"] == "abc123hash"
