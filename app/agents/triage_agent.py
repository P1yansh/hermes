import re
from datetime import datetime, timezone
from app.config import settings, to_utc
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.connectors.google_live import GoogleLiveConnector
from app.db import db
from app.models.academic import ExtractedTask
from app.services.gemma_client import gemma_client

SPAM_SENDERS = [
    "promotions@", "newsletter@", "marketing@", "noreply@store", "campusbooks", "studentcouncil"
]
SPAM_KEYWORDS = [
    "sale", "discount", "hoodies", "merchandise", "unsubscribe", "movie night", "yoga club", "lost & found"
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
    def is_promotional_or_spam(sender: str, subject: str, body: str) -> bool:
        """Stage-1 pre-filter: Drop marketing and community chatter without spending LLM tokens."""
        sender_lower = sender.lower()
        if any(s in sender_lower for s in SPAM_SENDERS):
            return True
        corpus = f"{subject} {body}".lower()
        if any(k in corpus for k in SPAM_KEYWORDS):
            # If it's a promotional keyword and doesn't explicitly state an assignment due, drop it
            if not any(d in corpus for d in ["due", "assignment", "lab", "midterm", "exam", "homework"]):
                return True
        return False

    async def triage(self, force_refresh: bool = False) -> list[ExtractedTask]:
        """
        Gathers raw inboxes and classroom streams, filtering spam
        and extracting structured deadlines via Gemma.
        Persists extracted tasks to SQLite and skips already-seen items.
        """
        if not force_refresh:
            cached_tasks = db.get_all_tasks()
            if cached_tasks:
                return cached_tasks

        new_tasks: list[ExtractedTask] = []

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
                        confidence=1.0
                    )
                )

        # 2. Process emails with Stage-1 pre-filter + Gemma 2 extraction
        emails = await self.connector.get_recent_emails(max_results=15)
        for msg in emails:
            if not force_refresh and db.is_item_seen(msg.id):
                continue

            # Stage-1 Pre-filter: Drop obvious promotions without wasting GPU inference
            if self.is_promotional_or_spam(msg.sender, msg.subject, msg.body):
                db.mark_item_seen(msg.id, "email")
                continue

            # Stage-2: Gemma 2 Structured Extraction
            extraction = await gemma_client.extract_email_task(
                sender=msg.sender,
                subject=msg.subject,
                body=msg.body
            )

            if extraction.get("has_action") and not extraction.get("is_spam"):
                now = datetime.now(timezone.utc)
                deadline_text = extraction.get("deadline_text", "").lower()
                if "tonight" in deadline_text:
                    approx_deadline = now.replace(hour=23, minute=59, second=0)
                elif "tomorrow" in deadline_text:
                    approx_deadline = now.replace(hour=18, minute=0, second=0)
                else:
                    approx_deadline = now

                new_tasks.append(
                    ExtractedTask(
                        source_type="email",
                        source_id=msg.id,
                        course_or_sender=extraction.get("course", msg.sender),
                        title=extraction.get("title", msg.subject),
                        deadline=to_utc(approx_deadline),
                        action_required=extraction.get("action_required", "Check email instructions"),
                        is_urgent=True if "tonight" in deadline_text else False,
                        submission_url=None,
                        estimated_hours=extraction.get("estimated_hours", 1.5),
                        confidence=0.9
                    )
                )
            else:
                db.mark_item_seen(msg.id, "email")

        # Save to SQLite persistence layer
        if new_tasks:
            db.save_tasks(new_tasks)

        return db.get_all_tasks()

triage_agent = AcademicTriageAgent()
