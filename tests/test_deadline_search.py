import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from app.db import Database
from app.tools.deadline_search import SearchDeadlineTool

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_search.db"
    database = Database(db_path=str(db_file))
    database.init_db()
    return database

@pytest.mark.asyncio
async def test_search_cache_hits(temp_db, monkeypatch):
    monkeypatch.setattr("app.tools.deadline_search.db", temp_db)
    tool = SearchDeadlineTool(serpapi_key="test_key")

    future_dt = datetime.now(timezone.utc) + timedelta(days=5)
    temp_db.save_cached_deadline("smart-india-hackathon", "smart india hackathon 2026 deadline", future_dt.isoformat())

    # Should hit cache without making network calls
    with patch.object(tool, "search_snippets", new_callable=AsyncMock) as mock_search:
        resolved, has_deadline = await tool.resolve_deadline("smart-india-hackathon")
        assert has_deadline is True
        assert resolved is not None
        assert mock_search.call_count == 0

@pytest.mark.asyncio
async def test_negative_search_cache(temp_db, monkeypatch):
    monkeypatch.setattr("app.tools.deadline_search.db", temp_db)
    tool = SearchDeadlineTool(serpapi_key="test_key")

    # Cache as negative lookup (no deadline found)
    temp_db.save_cached_deadline("open-source-fellowship", "open source fellowship 2026 deadline", None)

    with patch.object(tool, "search_snippets", new_callable=AsyncMock) as mock_search:
        resolved, has_deadline = await tool.resolve_deadline("open-source-fellowship")
        assert has_deadline is False
        assert resolved is None
        assert mock_search.call_count == 0

@pytest.mark.asyncio
async def test_resolve_deadline_via_gemma_fallback(temp_db, monkeypatch):
    monkeypatch.setattr("app.tools.deadline_search.db", temp_db)
    tool = SearchDeadlineTool(serpapi_key="test_key")

    mock_snippets = [
        "Desis Ascend Fellowship 2026: Submissions close on Nov 15, 2026 at 11:59 PM.",
        "Eligible female engineering students can register before November 15, 2026."
    ]

    with patch.object(tool, "search_snippets", new_callable=AsyncMock, return_value=mock_snippets):
        resolved, has_deadline = await tool.resolve_deadline("Desis Ascend Fellowship")
        assert has_deadline is True
        assert resolved is not None
        assert resolved.month == 11
        assert resolved.day == 15

        # Verify it cached to DB
        is_cached, cached_iso = temp_db.get_cached_deadline("desis-ascend-fellowship")
        assert is_cached is True
        assert cached_iso is not None
