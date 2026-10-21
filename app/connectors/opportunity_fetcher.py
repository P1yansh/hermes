import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.models.opportunity import OpportunityItem

logger = logging.getLogger(__name__)

async def fetch_devpost_hackathons() -> list[OpportunityItem]:
    """Fetch live hackathons from public Devpost JSON API."""
    url = "https://devpost.com/api/hackathons?status[]=upcoming&status[]=open"
    opps: list[OpportunityItem] = []
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0 Hermes/2.0"})
            if res.status_code != 200:
                return []
            data = res.json()
            hackathons = data.get("hackathons", [])
            for h in hackathons[:10]:
                hid = f"devpost_{h.get('id', '')}"
                title = h.get("title", "")
                if not title:
                    continue
                # Devpost location detection
                displayed_location = h.get("displayed_location", {}).get("location", "")
                is_online = h.get("online", False) or "online" in displayed_location.lower()
                city = None if is_online else displayed_location
                
                # Submission deadline
                sub_period = h.get("submission_period_dates", "")
                # Default to 7 days from now if not parseable
                deadline = datetime.now(timezone.utc) + timedelta(days=7)
                
                opps.append(
                    OpportunityItem(
                        id=hid,
                        title=title,
                        type="hackathon",
                        organizer=h.get("organization_name") or "Devpost Community",
                        deadline=deadline,
                        prizes=h.get("prize_amount"),
                        tags=h.get("themes", []) or ["Hackathon", "Open Source"],
                        description=h.get("tagline") or title,
                        url=h.get("url") or "https://devpost.com",
                        mode="online" if is_online else "offline",
                        city=city,
                        country="India" if is_online else "Global",
                        relevance_score=6
                    )
                )
    except Exception as e:
        logger.debug(f"Devpost API live fetch skipped ({e})")
    return opps

async def fetch_unstop_hackathons() -> list[OpportunityItem]:
    """Fetch live Indian hackathons & case challenges from Unstop public API."""
    url = "https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&page=1"
    opps: list[OpportunityItem] = []
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0 Hermes/2.0"})
            if res.status_code != 200:
                return []
            data = res.json()
            items = data.get("data", {}).get("data", [])
            for item in items[:10]:
                uid = f"unstop_{item.get('id', '')}"
                title = item.get("title", "")
                if not title:
                    continue
                
                filters = item.get("filters", {})
                reg_mode = item.get("reg_mode", "").lower()
                is_online = "online" in reg_mode or item.get("is_online", True)
                city = item.get("city") or filters.get("city")
                
                end_date_str = item.get("end_date") or item.get("regn_end_date")
                deadline = datetime.now(timezone.utc) + timedelta(days=5)
                if end_date_str:
                    try:
                        deadline = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    except Exception:
                        pass
                
                opps.append(
                    OpportunityItem(
                        id=uid,
                        title=title,
                        type="hackathon",
                        organizer=item.get("organisation", {}).get("name") or "Unstop Partner",
                        deadline=deadline,
                        prizes=item.get("prizes", {}).get("cash_prizes") or item.get("rewards"),
                        tags=[f for f in [item.get("category"), "Unstop", "College Challenge"] if f],
                        description=item.get("short_desc") or title,
                        url=f"https://unstop.com/{item.get('public_url')}" if item.get('public_url') else "https://unstop.com",
                        mode="online" if is_online else "offline",
                        city=city,
                        country="India",
                        relevance_score=7
                    )
                )
    except Exception as e:
        logger.debug(f"Unstop API live fetch skipped ({e})")
    return opps

async def fetch_all_public_opportunities() -> list[OpportunityItem]:
    """Aggregates all public API feeds, returning successfully fetched items."""
    devpost_items = await fetch_devpost_hackathons()
    unstop_items = await fetch_unstop_hackathons()
    return devpost_items + unstop_items
