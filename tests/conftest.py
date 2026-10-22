import pytest
from pathlib import Path
from app.config import settings
from app.agents.triage_agent import triage_agent
from app.agents.scout_agent import scout_agent
from app.connectors.mock_loader import MockConnector
from app.db import db

@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch, tmp_path):
    """
    Ensure all automated tests run deterministically offline using MockConnector,
    isolated temporary SQLite database, and never touch production hermes.db or live network.
    """
    test_db_path = tmp_path / "hermes_test.db"
    monkeypatch.setattr(settings, "DATA_SOURCE", "mock")
    monkeypatch.setattr(settings, "DATABASE_PATH", str(test_db_path))
    monkeypatch.setattr(db, "db_path", test_db_path)
    db.init_db()
    monkeypatch.setattr(triage_agent, "connector", MockConnector())
    monkeypatch.setattr(scout_agent, "connector", MockConnector())
