import pytest
from datetime import datetime, timezone
from app.connectors.google_live import GoogleLiveConnector
from app.models.opportunity import OpportunityItem
from app.agents.scout_agent import is_geo_eligible, score_opportunity, TARGET_COMPANIES
from app.agents.triage_agent import AcademicTriageAgent

def test_multi_account_loading():
    connector = GoogleLiveConnector(accounts_config_path="config/accounts.json")
    assert len(connector.accounts) == 3
    
    college_acc = next(a for a in connector.accounts if a["id"] == "college_iiitl")
    assert college_acc["enable_gmail"] is True
    assert college_acc["enable_classroom"] is True
    
    personal_acc = next(a for a in connector.accounts if a["id"] == "personal_primary")
    assert personal_acc["enable_gmail"] is True
    assert personal_acc["enable_classroom"] is False

def test_geo_fencing_rules():
    # 1. Offline hackathon in Lucknow -> KEEP
    lucknow_hack = OpportunityItem(
        id="opp_lko",
        title="HackIIITL 2026",
        type="hackathon",
        organizer="IIIT Lucknow",
        deadline=datetime.now(timezone.utc),
        tags=["Python"],
        description="Local hackathon",
        url="https://iiitl.ac.in",
        mode="offline",
        city="Lucknow",
        country="India"
    )
    eligible, reason = is_geo_eligible(lucknow_hack)
    assert eligible is True
    assert "Lucknow" in reason

    # 2. Offline hackathon in Bengaluru -> DROP (outside Lucknow)
    blr_hack = OpportunityItem(
        id="opp_blr",
        title="Bangalore Tech Fest Hackathon",
        type="hackathon",
        organizer="TechHub BLR",
        deadline=datetime.now(timezone.utc),
        tags=["Python"],
        description="Physical hackathon in Koramangala",
        url="https://example.com",
        mode="offline",
        city="Bengaluru",
        country="India"
    )
    eligible, reason = is_geo_eligible(blr_hack)
    assert eligible is False
    assert "outside Lucknow" in reason

    # 3. Online hackathon -> KEEP
    online_hack = OpportunityItem(
        id="opp_online",
        title="Global Agent Hackathon",
        type="hackathon",
        organizer="OpenAI / Devpost",
        deadline=datetime.now(timezone.utc),
        tags=["AI"],
        description="Virtual online competition",
        url="https://example.com",
        mode="online",
        country="India"
    )
    eligible, reason = is_geo_eligible(online_hack)
    assert eligible is True
    assert "Online" in reason

    # 4. Foreign country restriction -> DROP
    us_hack = OpportunityItem(
        id="opp_us",
        title="US Residents Only Challenge",
        type="hackathon",
        organizer="US Dept of Tech",
        deadline=datetime.now(timezone.utc),
        tags=["Python"],
        description="Must be US citizen",
        url="https://example.com",
        mode="online",
        country="United States"
    )
    eligible, reason = is_geo_eligible(us_hack)
    assert eligible is False
    assert "Restricted to United States" in reason

def test_company_tier_scoring():
    deshaw_opp = OpportunityItem(
        id="opp_deshaw",
        title="DESIS Ascend Educare Program 2026",
        type="internship",
        organizer="D. E. Shaw India",
        deadline=datetime.now(timezone.utc),
        tags=["Python", "C++"],
        description="Flagship mentorship and internship program from D. E. Shaw",
        url="https://deshaw.com",
        mode="online",
        country="India"
    )
    result = score_opportunity(deshaw_opp, ["Python", "C++"])
    assert result["eligible"] is True
    assert result["matched_company"] in ("d. e. shaw", "de shaw", "desis")
    assert result["score"] >= 80  # Base 50 + 40 company + 30 skills (capped at 100)
    assert deshaw_opp.relevance_score >= 8

def test_stage1_email_intent_classifier():
    # Opportunity email
    assert AcademicTriageAgent.classify_email_intent(
        sender="noreply@unstop.com",
        subject="Flipkart GRiD 6.0 Registration Open!",
        body="Register your team for the robotics and ML track."
    ) == "opportunity"

    assert AcademicTriageAgent.classify_email_intent(
        sender="jobalerts-noreply@linkedin.com",
        subject="Uber is hiring for Software Engineering Intern",
        body="View job details and apply on Greenhouse."
    ) == "opportunity"

    # Marketing spam
    assert AcademicTriageAgent.classify_email_intent(
        sender="campusbooks@university.edu",
        subject="50% Off On All College Hoodies and Merchandise",
        body="Flash sale ending this weekend. Unsubscribe here."
    ) == "spam"

    # Academic assignment
    assert AcademicTriageAgent.classify_email_intent(
        sender="prof.sharma@iiitl.ac.in",
        subject="CS301 Lab 3 Due Date Extension",
        body="Problem Set 3 is now due on Friday at 11:59 PM. Please submit your github repo."
    ) == "academic"
