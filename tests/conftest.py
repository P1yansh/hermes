import pytest
from app.config import settings
from app.agents.triage_agent import triage_agent
from app.agents.scout_agent import scout_agent
from app.connectors.mock_loader import MockConnector
from app.db import db

@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """
    Ensure all automated tests run deterministically offline using MockConnector
    and never hang on live OAuth or external network calls.
    """
    monkeypatch.setattr(settings, "DATA_SOURCE", "mock")
    monkeypatch.setattr(triage_agent, "connector", MockConnector())
    monkeypatch.setattr(scout_agent, "connector", MockConnector())
