import html
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from app.config import settings, to_utc
from app.models.opportunity import OpportunityItem

logger = logging.getLogger(__name__)

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _clean_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", "", str(value))).strip()
    return text or None


def _end_of_day(year: int, month: int, day: int) -> Optional[datetime]:
    """Turn a date with no published time into the end of that day in IST."""
    try:
        tz = ZoneInfo(settings.USER_TIMEZONE)
        return to_utc(datetime(year, month, day, 23, 59, 59, tzinfo=tz))
    except Exception:
        return None


def parse_devpost_deadline(raw: Optional[str]) -> Optional[datetime]:
    """Parse Devpost's submission_period_dates without inventing a date.

    Supported shapes: "Aug 31 - Oct 23, 2026", "Oct 23 - 25, 2026",
    "Nov 15, 2026", and ISO-8601 strings.
    """
    if not raw:
        return None
    text = str(raw).strip()

    iso_match = re.search(r"(\d{4}-\d{2}-\d{2}(?:T[0-9:.+\-Z]+)?)", text)
    if iso_match:
        try:
            iso_value = iso_match.group(1).replace("Z", "+00:00")
            if len(iso_value) == 10:
                year, month, day = (int(part) for part in iso_value.split("-"))
                return _end_of_day(year, month, day)
            return to_utc(datetime.fromisoformat(iso_value))
        except Exception:
            return None

    # Cross-year ranges ("Dec 15, 2026 - Jan 15, 2027") must use the final
    # date, not the first one. Check this before the shorter range pattern.
    full_range = re.search(
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\s*[-\u2013]\s*"
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})",
        text,
    )
    if full_range:
        _month1, _day1, _year1, month2, day2, year2 = full_range.groups()
        month = MONTHS.get(month2[:3].lower())
        if month:
            return _end_of_day(int(year2), month, int(day2))

    range_match = re.search(
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*[-\u2013]\s*"
        r"(?:([A-Za-z]{3,9})\.?\s+)?(\d{1,2}),?\s+(\d{4})",
        text,
    )
    if range_match:
        month1, day1, month2, day2, year = range_match.groups()
        month_name = (month2 or month1)[:3].lower()
        month = MONTHS.get(month_name)
        if month:
            return _end_of_day(int(year), month, int(day2))

    single_match = re.search(
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})",
        text,
    )
    if single_match:
        month_name, day, year = single_match.groups()
        month = MONTHS.get(month_name[:3].lower())
        if month:
            return _end_of_day(int(year), month, int(day))

    return None


def parse_unstop_deadline(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    value = str(raw).strip().replace("Z", "+00:00")
    try:
        if len(value) == 10:
            year, month, day = (int(part) for part in value.split("-"))
            return _end_of_day(year, month, day)
        return to_utc(datetime.fromisoformat(value))
    except Exception:
        return None


async def fetch_devpost_hackathons() -> list[OpportunityItem]:
    """Fetch live hackathons from the public Devpost JSON API."""
    url = "https://devpost.com/api/hackathons?status[]=upcoming&status[]=open"
    opps: list[OpportunityItem] = []
    now = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0 Hermes/2.0"})
            if res.status_code != 200:
                return []
            data = res.json()
            for h in data.get("hackathons", [])[:10]:
                title = h.get("title", "")
                if not title:
                    continue

                displayed_location = (h.get("displayed_location") or {}).get("location", "")
                is_online = bool(h.get("online")) or "online" in displayed_location.lower()
                deadline = parse_devpost_deadline(h.get("submission_period_dates"))
                if deadline and deadline < now:
                    continue

                themes = h.get("themes") or []
                tags = [
                    t.get("name") for t in themes
                    if isinstance(t, dict) and t.get("name")
                ] or ["Hackathon", "Open Source"]

                opps.append(
                    OpportunityItem(
                        id=f"devpost_{h.get('id', '')}",
                        title=title,
                        type="hackathon",
                        organizer=h.get("organization_name") or "Devpost Community",
                        deadline=deadline,
                        prizes=_clean_text(h.get("prize_amount")),
                        tags=tags,
                        description=h.get("tagline") or title,
                        url=h.get("url") or "https://devpost.com",
                        mode="online" if is_online else "offline",
                        city=None if is_online else displayed_location or None,
                        country="Global",
                        relevance_score=6,
                        has_explicit_deadline=deadline is not None,
                    )
                )
    except Exception as e:
        logger.debug(f"Devpost API live fetch skipped ({e})")
    return opps


async def fetch_unstop_hackathons() -> list[OpportunityItem]:
    """Fetch live Indian hackathons from the public Unstop API."""
    url = "https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&page=1"
    opps: list[OpportunityItem] = []
    now = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0 Hermes/2.0"})
            if res.status_code != 200:
                return []
            data = res.json()
            for item in data.get("data", {}).get("data", [])[:10]:
                title = item.get("title", "")
                if not title:
                    continue

                deadline = parse_unstop_deadline(item.get("end_date")) or parse_unstop_deadline(
                    item.get("regn_end_date")
                )
                if deadline and deadline < now:
                    continue

                region = (item.get("region") or "").lower()
                filters = item.get("filters")
                filter_names = [
                    f.get("name") for f in filters
                    if isinstance(f, dict) and f.get("name")
                ] if isinstance(filters, list) else []
                tags = [t for t in filter_names if t in {"Hackathon", "Coding Challenge", "AI/ML", "Web Development"}]
                tags = (tags or ["Unstop", "College Challenge"])[:4]

                prizes_data = item.get("prizes")
                prize_text = None
                if isinstance(prizes_data, list) and prizes_data:
                    first_prize = prizes_data[0]
                    if isinstance(first_prize, dict):
                        cash = first_prize.get("cash")
                        currency = first_prize.get("currencyCode") or first_prize.get("currency")
                        if cash is not None:
                            prize_text = f"{currency or 'INR'} {cash}"
                        elif first_prize.get("others"):
                            prize_text = str(first_prize["others"])
                elif isinstance(prizes_data, dict):
                    prize_text = prizes_data.get("cash_prizes")

                organizer = (item.get("organisation") or {}).get("name") or "Unstop Partner"

                opps.append(
                    OpportunityItem(
                        id=f"unstop_{item.get('id', '')}",
                        title=title,
                        type="hackathon",
                        organizer=organizer,
                        deadline=deadline,
                        prizes=_clean_text(prize_text or item.get("rewards")),
                        tags=tags,
                        description=item.get("short_desc") or title,
                        url=(
                            f"https://unstop.com/{item.get('public_url')}"
                            if item.get("public_url") else "https://unstop.com"
                        ),
                        mode="online" if region == "online" else "offline",
                        city=item.get("city"),
                        country="India",
                        relevance_score=7,
                        has_explicit_deadline=deadline is not None,
                    )
                )
    except Exception as e:
        logger.debug(f"Unstop API live fetch skipped ({e})")
    return opps


async def fetch_all_public_opportunities() -> list[OpportunityItem]:
    """Aggregate all public API feeds, returning successfully fetched items."""
    devpost_items = await fetch_devpost_hackathons()
    unstop_items = await fetch_unstop_hackathons()
    return devpost_items + unstop_items
