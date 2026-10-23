from unittest.mock import AsyncMock

import pytest

from app.agents.scout_agent import scout_agent
from app.agents.triage_agent import triage_agent
from app.config import settings
from app.connectors.mock_loader import MockConnector
from app.db import db
from app.services.elevenlabs import elevenlabs_service
from app.services.gemma_client import gemma_client
from app.tools.deadline_search import deadline_search_tool


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch, tmp_path):
    """
    Keep tests deterministic and offline: temporary SQLite file, mock
    connectors, no llama-server calls, no ElevenLabs calls, and no web search.
    """
    test_db_path = tmp_path / "hermes_test.db"
    audio_dir = tmp_path / "audio_cache"
    audio_dir.mkdir()

    monkeypatch.setattr(settings, "DATA_SOURCE", "mock")
    monkeypatch.setattr(settings, "DATABASE_PATH", str(test_db_path))
    monkeypatch.setattr(db, "db_path", test_db_path)
    monkeypatch.setattr("app.services.elevenlabs.AUDIO_CACHE_DIR", audio_dir)
    monkeypatch.setattr(elevenlabs_service, "api_key", "")
    monkeypatch.setattr(gemma_client, "_call_chat", AsyncMock(return_value=None))
    monkeypatch.setattr(deadline_search_tool, "search_snippets", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.agents.scout_agent.fetch_all_public_opportunities",
        AsyncMock(return_value=[]),
    )

    db.init_db()
    monkeypatch.setattr(triage_agent, "connector", MockConnector())
    monkeypatch.setattr(scout_agent, "connector", MockConnector())
