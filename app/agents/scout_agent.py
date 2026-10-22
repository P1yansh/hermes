import logging
from datetime import datetime, timezone
from typing import Optional
from app.config import settings, to_utc
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.connectors.google_live import GoogleLiveConnector
from app.connectors.opportunity_fetcher import fetch_all_public_opportunities
from app.db import db
from app.models.opportunity import OpportunityItem, UserProfile, ScoutReport
from app.tools.deadline_search import deadline_search_tool

logger = logging.getLogger(__name__)

TARGET_COMPANIES = {
    # HFTs & Quant / Banking
    "d. e. shaw": 40, "de shaw": 40, "desis": 40,
    "jp morgan": 35, "jpmorgan": 35, "jpmc": 35, "code for good": 40,
    "goldman sachs": 35, "morgan stanley": 30,
    "tower research": 40, "quadeye": 40, "alphagrep": 40, "graviton": 40,
    # High-Growth Tech & FinTech
    "uber": 35, "uber hacktag": 40,
    "zomato": 35, "blinkit": 30,
    "paypal": 35, "stripe": 35, "razorpay": 30,
    "atlassian": 35, "rubrik": 35, "databricks": 35,
    # Big Tech
    "google": 35, "amazon": 30, "microsoft": 30, "meta": 35, "apple": 30,
}

USER_LOCATION = {
    "city": settings.USER_CITY.lower(),
    "state": settings.USER_STATE.lower(),
    "country": settings.USER_COUNTRY.lower(),
    "university": "iiit lucknow",
    "graduation_year": 2029,
}

def is_geo_eligible(opp: OpportunityItem) -> tuple[bool, str]:
    """
    Hard Geo-Fence Rule:
    - If country not India/Global -> DROP
    - If Hackathon/Workshop is offline outside Lucknow -> DROP
    - If Online or Offline in Lucknow -> KEEP
    - Internships / Fellowships / Grants in India or Remote -> KEEP
    """
    mode = (opp.mode or "online").lower()
    city = (opp.city or "").lower()
    country = (opp.country or "india").lower()

    # 1. Country Check
    if country not in ("india", "global", "worldwide", "all", ""):
        return False, f"Restricted to {opp.country}"

    # 2. Mode & City Check for Hackathons and Workshops
    if opp.type in ("hackathon", "workshop", "academic_program"):
        if mode == "online":
            return True, "Online (India/Global Eligible)"
        if "lucknow" in city or "iiit lucknow" in city or "iiitl" in city:
            return True, "Offline — Local (Lucknow)"
        return False, f"Offline outside Lucknow ({opp.city or 'Unspecified City'})"

    # 3. Internships, Fellowships, Grants are accessible across major hubs / remote
    return True, f"{opp.type.capitalize()} ({opp.city or 'India/Remote'})"

def score_opportunity(opp: OpportunityItem, user_skills: list[str]) -> dict:
    """
    Scores an opportunity against target company tiers, user skill overlap,
    and Lucknow locality bonus.
    """
    eligible, reason = is_geo_eligible(opp)
    opp.eligible = eligible
    opp.eligibility_reason = reason

    if not eligible:
        opp.relevance_score = 1
        opp.match_score = 10
        return {"eligible": False, "score": 10, "matched_skills": [], "reason": reason}

    # Base baseline for open eligible events
    score = 50
    haystack = f"{opp.title} {opp.organizer} {' '.join(opp.tags)} {opp.description}".lower()

    # 1. Company Tier Boost
    matched_company = None
    for company, boost in TARGET_COMPANIES.items():
        if company in haystack:
            score += boost
            matched_company = company
            break

    # 2. Skill Vector Overlap
    matched_skills = []
    for s in user_skills:
        s_clean = s.lower().strip()
        if not s_clean:
            continue
        if s_clean in haystack or any(s_clean == t.lower().strip() for t in opp.tags):
            matched_skills.append(s)

    score += min(45, len(matched_skills) * 15)

    # 3. Local Lucknow Offline Bonus
    city_lower = (opp.city or "").lower()
    if "lucknow" in city_lower or "iiit lucknow" in city_lower:
        score += 20

    final_match_score = min(100, score)
    # Scale 1-10 for relevance_score
    relevance_10 = max(1, min(10, round(final_match_score / 10)))

    opp.relevance_score = relevance_10
    opp.match_score = final_match_score

    return {
        "eligible": True,
        "score": final_match_score,
        "matched_skills": matched_skills,
        "matched_company": matched_company,
        "reason": reason
    }

class OpportunityScoutAgent:
    def __init__(self, connector: BaseConnector | None = None):
        if connector:
            self.connector = connector
        elif settings.DATA_SOURCE == "live":
            self.connector = GoogleLiveConnector(
                credentials_path=settings.GOOGLE_CREDENTIALS_PATH,
                token_path=settings.GOOGLE_TOKEN_PATH
            )
        else:
            self.connector = MockConnector()

    async def scout(self, profile: UserProfile | None = None, force_refresh: bool = False) -> ScoutReport:
        if profile is None:
            profile = UserProfile()

        far_future = datetime.max.replace(tzinfo=timezone.utc)

        # Check cached opportunities
        if not force_refresh:
            cached_opps = db.get_all_opportunities()
            if cached_opps:
                # Re-score cached opportunities if custom skills are provided
                scored_cached: list[OpportunityItem] = []
                for opp in cached_opps:
                    score_opportunity(opp, profile.skills)
                    if opp.eligible and opp.relevance_score >= profile.min_prize_relevance:
                        scored_cached.append(opp)
                scored_cached.sort(key=lambda x: (-(x.match_score or x.relevance_score * 10), x.deadline or far_future))
                return ScoutReport(total_found=len(scored_cached), matches=scored_cached)

        # 1. Fetch from primary connector
        raw_opportunities = await self.connector.get_opportunities()

        # 2. Fetch from live public APIs if running in live mode or requested
        if settings.DATA_SOURCE == "live" or force_refresh:
            try:
                public_opps = await fetch_all_public_opportunities()
                raw_opportunities.extend(public_opps)
            except Exception as e:
                logger.debug(f"Public API fetch skipped: {e}")

        # 3. Include opportunities mined from emails
        email_opps = [o for o in db.get_all_opportunities() if o.source_inbox]
        raw_opportunities.extend(email_opps)

        # 4. If still empty, fall back to curated catalog
        if not raw_opportunities:
            raw_opportunities = await MockConnector().get_opportunities()

        scored_matches: list[OpportunityItem] = []
        seen_ids = set()

        for opp in raw_opportunities:
            if opp.id in seen_ids:
                continue
            seen_ids.add(opp.id)

            score_data = score_opportunity(opp, profile.skills)
            opp.deadline = to_utc(opp.deadline) if opp.deadline else None

            # Attempt autonomous web search if deadline is missing and opportunity is eligible
            if opp.deadline is None and opp.eligible:
                resolved_deadline, has_deadline = await deadline_search_tool.resolve_deadline(opp.title)
                if resolved_deadline:
                    opp.deadline = resolved_deadline
                    opp.has_explicit_deadline = True
                else:
                    opp.has_explicit_deadline = False
            else:
                opp.has_explicit_deadline = (opp.deadline is not None)

            # Persist all opportunities to DB with eligibility state
            scored_matches.append(opp)

        # Save to SQLite
        if scored_matches:
            db.save_opportunities(scored_matches)

        # Filter down for the returned report
        eligible_matches = [
            o for o in scored_matches
            if o.eligible and o.relevance_score >= profile.min_prize_relevance
        ]
        eligible_matches.sort(key=lambda x: (-(x.match_score or x.relevance_score * 10), x.deadline or far_future))

        return ScoutReport(
            total_found=len(eligible_matches),
            matches=eligible_matches
        )

scout_agent = OpportunityScoutAgent()
