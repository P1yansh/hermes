import pytest
from datetime import datetime, timezone, timedelta

from app.db import Database, slugify
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


def test_sqlite_uses_wal_mode(test_db):
    with test_db.connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_slugify_keeps_round_qualifier():
    assert slugify("Hackathon (Round 1)") != slugify("Hackathon (Round 2)")
    assert slugify("Hackathon (Round 1)") == "hackathon-round-1"


def test_negative_deadline_cache_expires(test_db):
    test_db.save_cached_deadline("expired-event", "expired event deadline", None)
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    with test_db.connection() as conn:
        conn.execute(
            "UPDATE deadline_search_cache SET searched_at = ? WHERE event_key = ?",
            (old, "expired-event"),
        )

    is_cached, value = test_db.get_cached_deadline("expired-event")
    assert is_cached is False
    assert value is None
    with test_db.connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM deadline_search_cache WHERE event_key = ?", ("expired-event",)
        ).fetchone()
    assert row is None


def test_ingestion_batch_writes_all_three_tables(test_db):
    task = ExtractedTask(
        source_type="email",
        source_id="msg_batch",
        course_or_sender="CS401",
        title="Batch Task",
        deadline=datetime.now(timezone.utc) + timedelta(hours=4),
        action_required="Submit",
        has_explicit_deadline=True,
    )
    opp = OpportunityItem(
        id="opp_batch",
        title="Batch Hackathon",
        type="hackathon",
        organizer="DEV",
        deadline=datetime.now(timezone.utc) + timedelta(days=2),
        description="Build",
        url="https://example.com",
        has_explicit_deadline=True,
    )
    ledger = [{
        "account_id": "college",
        "message_id": "msg_batch",
        "classification": "ACADEMIC_DEADLINE",
        "thread_id": "th_batch",
        "extracted_entity_id": "email_msg_batch",
        "llm_tokens_spent": 120,
    }]

    test_db.save_ingestion_batch([task], [opp], ledger)

    assert len(test_db.get_all_tasks()) == 1
    assert len(test_db.get_all_opportunities()) == 1
    assert test_db.is_email_in_ledger("college", "msg_batch")

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
        confidence=1.0,
        has_explicit_deadline=True,
        thread_id="th_raft_1",
        canonical_slug="raft-test"
    )
    test_db.save_tasks([task])
    assert test_db.is_item_seen("cw_999")

    tasks = test_db.get_all_tasks()
    assert len(tasks) == 1
    assert tasks[0].source_id == "cw_999"
    assert tasks[0].course_or_sender == "CS401"
    assert tasks[0].is_urgent is True
    assert tasks[0].has_explicit_deadline is True
    assert tasks[0].canonical_slug == "raft-test"

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
        relevance_score=9,
        has_explicit_deadline=True,
        thread_id="th_dev_1",
        canonical_slug="ai-hackathon"
    )
    test_db.save_opportunities([opp])
    assert test_db.is_item_seen("opp_test_1")

    opps = test_db.get_all_opportunities()
    assert len(opps) == 1
    assert opps[0].title == "AI Hackathon"
    assert opps[0].tags == ["python", "ai"]
    assert opps[0].has_explicit_deadline is True
    assert opps[0].canonical_slug == "ai-hackathon"

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

def test_email_ledger_crud(test_db):
    assert not test_db.is_email_in_ledger("college", "msg_001")

    test_db.record_email_ledger(
        account_id="college",
        message_id="msg_001",
        classification="INFORMATIONAL_ALERT",
        thread_id="th_alert",
        internal_date=1729584000000,
        subject="Welcome to SerpApi!",
        sender="contact@serpapi.com",
        llm_tokens_spent=0
    )

    assert test_db.is_email_in_ledger("college", "msg_001")
    assert not test_db.is_email_in_ledger("college", "msg_999")

    entry = test_db.get_ledger_entry("college", "msg_001")
    assert entry is not None
    assert entry["classification"] == "INFORMATIONAL_ALERT"
    assert entry["llm_tokens_spent"] == 0
    assert entry["subject"] == "Welcome to SerpApi!"

def test_deadline_search_cache_methods(test_db):
    # Miss
    is_cached, val = test_db.get_cached_deadline("unknown-event")
    assert not is_cached
    assert val is None

    # Positive hit
    test_db.save_cached_deadline("sih-2026", "smart india hackathon deadline", "2026-11-20T18:00:00Z")
    is_cached, val = test_db.get_cached_deadline("sih-2026")
    assert is_cached
    assert val == "2026-11-20T18:00:00Z"

    # Negative hit (unresolvable)
    test_db.save_cached_deadline("obscure-event", "obscure event deadline", None)
    is_cached, val = test_db.get_cached_deadline("obscure-event")
    assert is_cached
    assert val is None

def test_thread_and_slug_lookups(test_db):
    task = ExtractedTask(
        source_type="email",
        source_id="msg_t1",
        course_or_sender="Prof. X",
        title="Distributed Lab",
        action_required="Submit",
        thread_id="thread_abc",
        canonical_slug="distributed-lab"
    )
    test_db.save_tasks([task])

    found_by_thread = test_db.find_task_by_thread_or_slug("thread_abc", None)
    assert found_by_thread is not None
    assert found_by_thread.title == "Distributed Lab"

    found_by_slug = test_db.find_task_by_thread_or_slug(None, "distributed-lab")
    assert found_by_slug is not None
    assert found_by_slug.source_id == "msg_t1"
