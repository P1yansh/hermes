import pytest

from app.connectors import opportunity_fetcher


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return FakeResponse(self._payload)


def test_devpost_iso_z_is_parsed_as_utc():
    deadline = opportunity_fetcher.parse_devpost_deadline("2099-11-15T18:00:00Z")
    assert deadline is not None
    assert deadline.tzinfo is not None
    assert (deadline.hour, deadline.minute) == (18, 0)


def test_devpost_cross_year_range_uses_final_date():
    deadline = opportunity_fetcher.parse_devpost_deadline("Dec 15, 2098 - Jan 15, 2099")
    assert deadline is not None
    assert (deadline.year, deadline.month, deadline.day) == (2099, 1, 15)


def _patch_client(monkeypatch, payload):
    monkeypatch.setattr(
        opportunity_fetcher.httpx,
        "AsyncClient",
        lambda *args, **kwargs: FakeClient(payload),
    )


@pytest.mark.asyncio
async def test_devpost_missing_deadline_stays_none(monkeypatch):
    _patch_client(monkeypatch, {"hackathons": [{
        "id": 1,
        "title": "No Date Hackathon",
        "displayed_location": {"location": "Online"},
        "submission_period_dates": "Dates coming soon",
        "themes": [{"name": "AI"}],
        "url": "https://example.com",
    }]})

    opps = await opportunity_fetcher.fetch_devpost_hackathons()
    assert len(opps) == 1
    assert opps[0].deadline is None
    assert opps[0].has_explicit_deadline is False
    assert opps[0].tags == ["AI"]


@pytest.mark.asyncio
async def test_devpost_range_deadline_is_parsed(monkeypatch):
    _patch_client(monkeypatch, {"hackathons": [{
        "id": 2,
        "title": "Dated Hackathon",
        "displayed_location": {"location": "Online"},
        "submission_period_dates": "Aug 31 - Dec 30, 2099",
        "themes": [{"name": "AI"}],
        "url": "https://example.com",
    }]})

    opps = await opportunity_fetcher.fetch_devpost_hackathons()
    assert len(opps) == 1
    assert opps[0].deadline is not None
    assert (opps[0].deadline.year, opps[0].deadline.month, opps[0].deadline.day) == (2099, 12, 30)
    assert opps[0].has_explicit_deadline is True


@pytest.mark.asyncio
async def test_unstop_missing_or_invalid_date_stays_none(monkeypatch):
    _patch_client(monkeypatch, {"data": {"data": [{
        "id": 3,
        "title": "Undated Unstop Event",
        "end_date": None,
        "regn_end_date": "not-a-date",
        "region": "online",
        "organisation": {"name": "Unstop"},
        "public_url": "event",
    }]}})

    opps = await opportunity_fetcher.fetch_unstop_hackathons()
    assert len(opps) == 1
    assert opps[0].deadline is None
    assert opps[0].has_explicit_deadline is False


@pytest.mark.asyncio
async def test_unstop_valid_end_date_is_parsed(monkeypatch):
    _patch_client(monkeypatch, {"data": {"data": [{
        "id": 4,
        "title": "Dated Unstop Event",
        "end_date": "2099-11-20T18:00:00+05:30",
        "region": "online",
        "organisation": {"name": "Unstop"},
        "public_url": "event",
        "filters": [{"name": "Hackathon", "type": "category"}],
        "prizes": [{"cash": 5000, "currencyCode": "INR"}],
    }]}})

    opps = await opportunity_fetcher.fetch_unstop_hackathons()
    assert len(opps) == 1
    assert opps[0].deadline is not None
    assert opps[0].deadline.hour == 12  # 18:00 IST == 12:30 UTC
    assert opps[0].deadline.minute == 30
    assert opps[0].has_explicit_deadline is True
    assert opps[0].tags == ["Hackathon"]
    assert opps[0].prizes == "INR 5000"
