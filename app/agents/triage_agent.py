import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.config import settings, to_utc
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.connectors.google_live import GoogleLiveConnector
from app.db import db
from app.models.academic import ExtractedTask
from app.models.opportunity import OpportunityItem
from app.services.gemma_client import gemma_client

logger = logging.getLogger(__name__)

SPAM_SENDERS = [
    "promotions@", "newsletter@", "marketing@", "noreply@store", "campusbooks", "studentcouncil"
]
SPAM_KEYWORDS = [
    "sale", "discount", "hoodies", "merchandise", "unsubscribe", "movie night", "yoga club", "lost & found"
]

OPPORTUNITY_SENDERS = [
    "jobalerts-noreply@linkedin.com", "noreply@unstop.com", "devpost.com",
    "careers@", "recruitment@", "placement@", "training.placement@", "codingclub@"
]
OPPORTUNITY_KEYWORDS = [
    "hackathon", "internship", "fellowship", "code for good", "desis ascend",
    "hacktag", "unstop challenge", "stipend", "hiring challenge", "summer intern",
    "case challenge", "off-campus", "campus recruitment"
]

class AcademicTriageAgent:
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

    @staticmethod
    def classify_email_intent(sender: str, subject: str, body: str) -> str:
        """
        Stage-1 Router / Classifier:
        1. 'opportunity': Job alerts, Unstop, LinkedIn, hackathon announcements.
        2. 'spam': Commercial merchandise, flyers, promo emails without course deadlines.
        3. 'academic': Homework, quizzes, lab submissions, professor emails.
        """
        sender_lower = sender.lower()
        corpus = f"{subject} {body}".lower()

        # Opportunity check (Unstop, LinkedIn, placement cell, HFTs)
        if any(s in sender_lower for s in OPPORTUNITY_SENDERS) or any(k in corpus for k in OPPORTUNITY_KEYWORDS):
            return "opportunity"

        # Marketing / spam check
        if any(s in sender_lower for s in SPAM_SENDERS) or any(k in corpus for k in SPAM_KEYWORDS):
            if not any(d in corpus for d in ["due", "assignment", "lab", "midterm", "exam", "homework"]):
                return "spam"

        return "academic"

    @classmethod
    def is_promotional_or_spam(cls, sender: str, subject: str, body: str) -> bool:
        """Backwards-compatible helper: True if classified as pure spam."""
        return cls.classify_email_intent(sender, subject, body) == "spam"

    async def triage(self, force_refresh: bool = False) -> list[ExtractedTask]:
        """
        Gathers raw inboxes and classroom streams, filtering spam,
        routing opportunity alerts directly to Scout, and extracting
        structured deadlines via Gemma.
        """
        if not force_refresh:
            cached_tasks = db.get_all_tasks()
            if cached_tasks:
                return cached_tasks

        new_tasks: list[ExtractedTask] = []
        new_opps: list[OpportunityItem] = []

        # 1. Process Google Classroom coursework
        courses = await self.connector.get_classroom_courses()
        for course in courses:
            for a in course.assignments:
                if not force_refresh and db.is_item_seen(a.id):
                    continue

                new_tasks.append(
                    ExtractedTask(
                        source_type="classroom",
                        source_id=a.id,
                        course_or_sender=course.name,
                        title=a.title,
                        deadline=to_utc(a.due_at),
                        action_required=f"Submit '{a.title}' on Google Classroom",
                        is_urgent=False,
                        submission_url=a.submission_url,
                        estimated_hours=2.5,
                        confidence=1.0,
                        account_source=getattr(course, "account_source", "default")
                    )
                )

        # 2. Process emails with Stage-1 3-way Router
        emails = await self.connector.get_recent_emails(max_results=20)
        for msg in emails:
            if not force_refresh and db.is_item_seen(msg.id):
                continue

            intent = self.classify_email_intent(msg.sender, msg.subject, msg.body)

            if intent == "spam":
                # Drop without spending GPU inference
                db.mark_item_seen(msg.id, "email")
                continue

            elif intent == "opportunity":
                # Mine inbox for hackathon or job alert, route to Scout
                now = datetime.now(timezone.utc)
                deadline = now + timedelta(days=7)
                opp_type = "hackathon" if "hackathon" in f"{msg.subject} {msg.body}".lower() else "internship"
                organizer = msg.sender.split("<")[0].strip().replace('"', '') or "Opportunity Alert"
                
                new_opps.append(
                    OpportunityItem(
                        id=f"email_{msg.id}",
                        title=msg.subject,
                        type=opp_type,
                        organizer=organizer,
                        deadline=deadline,
                        tags=["Email Alert", msg.account_source or "inbox"],
                        description=msg.body[:300],
                        url="https://mail.google.com",
                        mode="online",
                        city="lucknow" if "lucknow" in f"{msg.subject} {msg.body}".lower() else None,
                        country="India",
                        source_inbox=msg.account_source,
                        relevance_score=8
                    )
                )
                db.mark_item_seen(msg.id, "email")
                continue

            # Stage-2: Academic Gemma Structured Extraction
            extraction = await gemma_client.extract_email_task(
                sender=msg.sender,
                subject=msg.subject,
                body=msg.body
            )

            if extraction.get("has_action") and not extraction.get("is_spam"):
                now = datetime.now(timezone.utc)
                deadline_text = (extraction.get("deadline_text") or "").lower()
                if "tonight" in deadline_text:
                    approx_deadline = now.replace(hour=23, minute=59, second=0)
                elif "tomorrow" in deadline_text:
                    approx_deadline = now.replace(hour=18, minute=0, second=0)
                else:
                    approx_deadline = now + timedelta(days=1)

                new_tasks.append(
                    ExtractedTask(
                        source_type="email",
                        source_id=msg.id,
                        course_or_sender=extraction.get("course") or msg.sender,
                        title=extraction.get("title") or msg.subject,
                        deadline=to_utc(approx_deadline),
                        action_required=extraction.get("action_required") or "Check email instructions",
                        is_urgent=True if "tonight" in deadline_text else False,
                        submission_url=None,
                        estimated_hours=float(extraction.get("estimated_hours") or 1.5),
                        confidence=0.9,
                        account_source=msg.account_source or "default"
                    )
                )
            else:
                db.mark_item_seen(msg.id, "email")

        # Save extracted tasks and mined opportunities to SQLite
        if new_tasks:
            db.save_tasks(new_tasks)

        if new_opps:
            db.save_opportunities(new_opps)

        return db.get_all_tasks()

triage_agent = AcademicTriageAgent()
