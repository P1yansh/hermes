import logging
from datetime import datetime, timezone
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
    local_city = settings.USER_CITY.strip().lower()
    if opp.type in ("hackathon", "workshop", "academic_program"):
        if mode == "online":
            return True, "Online (India/Global Eligible)"
        if local_city and local_city in city:
            return True, f"Offline — Local ({settings.USER_CITY.title()})"
        return False, f"Offline outside {settings.USER_CITY.title()} ({opp.city or 'Unspecified City'})"

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

    # 3. Local city offline bonus
    city_lower = (opp.city or "").lower()
    local_city = settings.USER_CITY.strip().lower()
    if local_city and local_city in city_lower:
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
        existing_opps = db.get_all_opportunities()
        existing_by_id = {o.id: o for o in existing_opps}
        existing_by_slug = {o.canonical_slug: o for o in existing_opps if o.canonical_slug}
        existing_by_thread = {o.thread_id: o for o in existing_opps if o.thread_id}

        # 1. Poll the primary connector on every sync. The ledger and the
        # existing rows decide what is new; a process-level cache does not.
        raw_opportunities = await self.connector.get_opportunities()

        # 2. Fetch from live public APIs in live mode. A forced mock refresh
        # also exercises the public feeds for demos that opt into them.
        if settings.DATA_SOURCE == "live" or force_refresh:
            try:
                public_opps = await fetch_all_public_opportunities()
                raw_opportunities.extend(public_opps)
            except Exception as e:
                logger.debug(f"Public API fetch skipped: {e}")

        # 3. Include opportunities mined from emails
        raw_opportunities.extend([o for o in existing_opps if o.source_inbox])

        # 4. In mock mode only, fall back to the curated catalog. In live mode
        # an empty connector result must stay empty.
        if not raw_opportunities and settings.DATA_SOURCE != "live":
            raw_opportunities = await MockConnector().get_opportunities()

        merged: dict[str, OpportunityItem] = {}
        for opp in raw_opportunities:
            existing = (
                existing_by_id.get(opp.id)
                or existing_by_thread.get(opp.thread_id)
                or existing_by_slug.get(opp.canonical_slug or "")
            )

            # Upstream feeds often omit a deadline on a later poll. Keep the
            # deadline we already resolved instead of erasing it.
            if existing and existing.deadline and not opp.deadline:
                opp.deadline = existing.deadline
                opp.has_explicit_deadline = existing.has_explicit_deadline

            score_opportunity(opp, profile.skills)
            opp.deadline = to_utc(opp.deadline) if opp.deadline else None

            if opp.deadline is None and opp.eligible:
                resolved_deadline, _ = await deadline_search_tool.resolve_deadline(opp.title)
                if resolved_deadline:
                    opp.deadline = resolved_deadline
                    opp.has_explicit_deadline = True
                else:
                    opp.has_explicit_deadline = False
            else:
                opp.has_explicit_deadline = opp.deadline is not None

            current = merged.get(opp.id)
            if current is None or (current.deadline is None and opp.deadline is not None):
                merged[opp.id] = opp

        scored_matches = list(merged.values())

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
