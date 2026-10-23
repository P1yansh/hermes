import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import settings, to_utc
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.connectors.google_live import GoogleLiveConnector
from app.db import db, slugify
from app.models.academic import ExtractedTask
from app.models.opportunity import OpportunityItem
from app.services.gemma_client import gemma_client
from app.tools.deadline_search import deadline_search_tool

logger = logging.getLogger(__name__)

INFORMATIONAL_SENDERS = [
    "no-reply@accounts.google.com", "accounts.google.com", "security@", "auth@",
    "login@", "billing@", "support@github.com", "orders@", "receipts@",
    "serpapi.com", "notifications@github.com", "verify@", "account-security-noreply@"
]

INFORMATIONAL_KEYWORDS = [
    "security alert", "passkey", "sign-in", "verification code", "welcome to",
    "subscription confirmed", "receipt for", "order confirmation", "invoice",
    "two-factor", "password reset", "account recovery", "otp", "2-step verification",
    "payment received", "billing update", "payment confirmation"
]

SPAM_SENDERS = [
    "promotions@", "newsletter@", "marketing@", "noreply@store", "campusbooks",
    "studentcouncil", "coupons@"
]

SPAM_KEYWORDS = [
    "sale", "discount", "hoodies", "merchandise", "unsubscribe", "movie night",
    "yoga club", "lost & found"
]

OPPORTUNITY_SENDERS = [
    "jobalerts-noreply@linkedin.com", "noreply@unstop.com", "devpost.com",
    "careers@", "recruitment@", "placement@", "training.placement@", "codingclub@",
    "hackathon@"
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
        Stage-1 Deterministic Filter & Classifier:
        1. 'informational': Welcome emails, security/passkey alerts, receipts, OTPs.
        2. 'spam': Commercial merchandise, store sales, hoodies, campus club flyers.
        3. 'opportunity': Job alerts, Unstop, LinkedIn, hackathon announcements.
        4. 'academic': Homework, quizzes, lab submissions, professor course emails.
        """
        sender_lower = sender.lower()
        corpus = f"{subject} {body}".lower()

        # 1. Informational & security alerts (0 LLM tokens)
        if any(s in sender_lower for s in INFORMATIONAL_SENDERS) or any(k in corpus for k in INFORMATIONAL_KEYWORDS):
            return "informational"

        # 2. Marketing & promotional spam (0 LLM tokens)
        if any(s in sender_lower for s in SPAM_SENDERS) or any(k in corpus for k in SPAM_KEYWORDS):
            academic_indicators = ["due", "assignment", "lab", "midterm", "exam", "homework", "quiz", "submission"]
            if not any(d in corpus for d in academic_indicators):
                return "spam"

        # 3. Opportunity check (Unstop, LinkedIn, placement cell, hackathons)
        if any(s in sender_lower for s in OPPORTUNITY_SENDERS) or any(k in corpus for k in OPPORTUNITY_KEYWORDS):
            return "opportunity"

        return "academic"

    @classmethod
    def is_promotional_or_spam(cls, sender: str, subject: str, body: str) -> bool:
        """Backwards-compatible helper: True if classified as spam or informational."""
        return cls.classify_email_intent(sender, subject, body) in ("spam", "informational")

    @staticmethod
    def resolve_relative_deadline(deadline_text: str, email_dt: datetime) -> Optional[datetime]:
        """Resolve 'tonight' / 'tomorrow' against the email's IST timestamp.

        The old code called .replace(hour=23, minute=59) on a UTC datetime. At
        20:00 IST that produced 05:29 IST the next day. Anchor in the user's
        timezone, then convert back to UTC for storage.
        """
        text = (deadline_text or "").lower()
        try:
            user_tz = ZoneInfo(settings.USER_TIMEZONE)
        except Exception:
            user_tz = timezone.utc

        email_ist = to_utc(email_dt).astimezone(user_tz)

        # Pull an explicit clock time out of the phrase when one exists:
        # "tomorrow at 5 PM" should stay 17:00 IST, not the 18:00 default.
        hour, minute = (23, 59) if "tonight" in text else (18, 0)
        if "midnight" in text:
            hour, minute = 0, 0
        elif "noon" in text:
            hour, minute = 12, 0
        else:
            time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text)
            if time_match:
                hour = int(time_match.group(1)) % 12
                minute = int(time_match.group(2) or 0)
                if time_match.group(3) == "pm":
                    hour += 12

        if "tonight" in text:
            return to_utc(email_ist.replace(hour=hour, minute=minute, second=0, microsecond=0))
        if "tomorrow" in text:
            tomorrow = (email_ist + timedelta(days=1)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return to_utc(tomorrow)
        return None

    async def triage(self, force_refresh: bool = False) -> list[ExtractedTask]:
        """
        Gathers raw inboxes and classroom streams, filtering spam/informational alerts,
        routing opportunity alerts directly to Scout, and extracting
        structured deadlines via Gemma with relative date anchoring.

        The connector is polled on every call. The email ledger, not a
        process-level cache, decides what has already been evaluated.
        """
        new_tasks: list[ExtractedTask] = []
        new_opps: list[OpportunityItem] = []
        ledger_entries: list[dict] = []

        # 1. Process Google Classroom coursework. This is a cheap API read and
        # re-running it lets an instructor's due-date change reach the radar.
        courses = await self.connector.get_classroom_courses()
        for course in courses:
            for a in course.assignments:
                slug = slugify(a.title)
                existing = db.find_task_by_thread_or_slug(None, slug)
                deadline_dt = to_utc(a.due_at) if a.due_at else None

                if existing and existing.deadline and not deadline_dt:
                    continue

                new_tasks.append(
                    ExtractedTask(
                        source_type="classroom",
                        source_id=a.id,
                        course_or_sender=course.name,
                        title=a.title,
                        deadline=deadline_dt,
                        action_required=f"Submit '{a.title}' on Google Classroom",
                        is_urgent=bool(
                            deadline_dt
                            and 0 <= (deadline_dt - datetime.now(timezone.utc)).total_seconds() < 21600
                        ),
                        submission_url=a.submission_url,
                        estimated_hours=2.5,
                        confidence=1.0,
                        account_source=getattr(course, "account_source", "default"),
                        has_explicit_deadline=bool(deadline_dt is not None),
                        thread_id=None,
                        canonical_slug=slug
                    )
                )

        # 2. Process emails with Stage-1 Deterministic Filter & Ledger
        emails = await self.connector.get_recent_emails(max_results=20)
        for msg in emails:
            account_id = msg.account_source or "default"

            # Check persistent ledger: skip already evaluated emails
            if not force_refresh and db.is_email_in_ledger(account_id, msg.id):
                continue

            # Compute relative timestamp anchor in IST
            if msg.internal_date:
                email_dt = datetime.fromtimestamp(msg.internal_date / 1000.0, tz=timezone.utc)
            else:
                email_dt = msg.received_at if msg.received_at else datetime.now(timezone.utc)

            try:
                user_tz = ZoneInfo(settings.USER_TIMEZONE)
            except Exception:
                user_tz = timezone.utc
            anchor_ist = email_dt.astimezone(user_tz).strftime("%Y-%m-%d %H:%M:%S %Z")

            intent = self.classify_email_intent(msg.sender, msg.subject, msg.body)

            if intent == "informational":
                # Record in ledger to never re-evaluate; drop completely from Radar & Watchlist
                ledger_entries.append({
                    "account_id": account_id,
                    "message_id": msg.id,
                    "classification": "INFORMATIONAL_ALERT",
                    "thread_id": msg.thread_id,
                    "internal_date": msg.internal_date,
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "llm_tokens_spent": 0,
                })
                continue

            elif intent == "spam":
                # Record in ledger; drop completely
                ledger_entries.append({
                    "account_id": account_id,
                    "message_id": msg.id,
                    "classification": "SPAM_NOISE",
                    "thread_id": msg.thread_id,
                    "internal_date": msg.internal_date,
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "llm_tokens_spent": 0,
                })
                continue

            elif intent == "opportunity":
                # Mine inbox for hackathon or job alert, route to Scout
                slug = slugify(msg.subject)
                existing_opp = db.find_opportunity_by_thread_or_slug(msg.thread_id, slug)

                # Attempt autonomous web search if no deadline is present in body
                resolved_deadline, has_deadline = await deadline_search_tool.resolve_deadline(
                    event_name=msg.subject,
                    anchor_ist=anchor_ist
                )
                if existing_opp and existing_opp.deadline and not resolved_deadline:
                    resolved_deadline = existing_opp.deadline
                    has_deadline = existing_opp.has_explicit_deadline

                opp_type = "hackathon" if "hackathon" in f"{msg.subject} {msg.body}".lower() else "internship"
                organizer = msg.sender.split("<")[0].strip().replace('"', '') or "Opportunity Alert"

                opp_id = f"email_{msg.id}"
                new_opps.append(
                    OpportunityItem(
                        id=opp_id,
                        title=msg.subject,
                        type=opp_type,
                        organizer=organizer,
                        deadline=resolved_deadline,
                        tags=["Email Alert", account_id],
                        description=msg.body[:300],
                        url="https://mail.google.com",
                        mode="online",
                        city="lucknow" if "lucknow" in f"{msg.subject} {msg.body}".lower() else None,
                        country="India",
                        source_inbox=account_id,
                        relevance_score=8,
                        has_explicit_deadline=has_deadline,
                        thread_id=msg.thread_id,
                        canonical_slug=slug
                    )
                )

                ledger_entries.append({
                    "account_id": account_id,
                    "message_id": msg.id,
                    "classification": "OPPORTUNITY_DEADLINE",
                    "thread_id": msg.thread_id,
                    "internal_date": msg.internal_date,
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "extracted_entity_id": opp_id,
                    "llm_tokens_spent": 0,
                })
                continue

            # Stage-2: Academic Gemma Structured Extraction
            extraction = await gemma_client.extract_email_task(
                sender=msg.sender,
                subject=msg.subject,
                body=msg.body,
                email_received_at_ist=anchor_ist
            )

            category = extraction.get("category", "ACADEMIC_DEADLINE")

            if category in ("INFORMATIONAL_ALERT", "SPAM_NOISE"):
                ledger_entries.append({
                    "account_id": account_id,
                    "message_id": msg.id,
                    "classification": category,
                    "thread_id": msg.thread_id,
                    "internal_date": msg.internal_date,
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "llm_tokens_spent": 50,
                })
                continue

            if category == "OPPORTUNITY_DEADLINE":
                slug = slugify(extraction.get("title") or msg.subject)
                existing_opp = db.find_opportunity_by_thread_or_slug(msg.thread_id, slug)
                resolved_deadline, has_deadline = await deadline_search_tool.resolve_deadline(
                    event_name=extraction.get("title") or msg.subject,
                    anchor_ist=anchor_ist
                )
                if existing_opp and existing_opp.deadline and not resolved_deadline:
                    resolved_deadline = existing_opp.deadline
                    has_deadline = existing_opp.has_explicit_deadline

                opp_id = f"email_{msg.id}"
                new_opps.append(
                    OpportunityItem(
                        id=opp_id,
                        title=extraction.get("title") or msg.subject,
                        type="hackathon" if "hackathon" in msg.subject.lower() else "internship",
                        organizer=extraction.get("course_or_organizer") or "Opportunity Alert",
                        deadline=resolved_deadline,
                        tags=["Email Alert", account_id],
                        description=msg.body[:300],
                        url="https://mail.google.com",
                        mode="online",
                        source_inbox=account_id,
                        relevance_score=8,
                        has_explicit_deadline=has_deadline,
                        thread_id=msg.thread_id,
                        canonical_slug=slug
                    )
                )
                ledger_entries.append({
                    "account_id": account_id,
                    "message_id": msg.id,
                    "classification": "OPPORTUNITY_DEADLINE",
                    "thread_id": msg.thread_id,
                    "internal_date": msg.internal_date,
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "extracted_entity_id": opp_id,
                    "llm_tokens_spent": 100,
                })
                continue

            # Handle legitimate ACADEMIC_DEADLINE. Relative phrases are anchored
            # deterministically in IST because a 4B model often treats "11:59 PM"
            # as UTC and silently shifts the deadline by 5.5 hours.
            slug = slugify(extraction.get("title") or msg.subject)
            deadline: Optional[datetime] = self.resolve_relative_deadline(
                extraction.get("deadline_text") or "",
                email_dt,
            )
            has_explicit_deadline = deadline is not None

            exact_iso = extraction.get("exact_deadline_iso")
            if deadline is None and exact_iso:
                try:
                    candidate = to_utc(datetime.fromisoformat(exact_iso))
                    # Reject obvious hallucinations. A real email can reference
                    # a recently missed cutoff, but not a deadline years away.
                    if email_dt - timedelta(days=30) <= candidate <= email_dt + timedelta(days=365):
                        deadline = candidate
                        has_explicit_deadline = True
                except Exception:
                    pass

            # Notice: If no deadline was extracted, deadline remains None and has_explicit_deadline = False!
            # Never fabricate a fake deadline.

            task_id = f"email_{msg.id}"
            new_tasks.append(
                ExtractedTask(
                    source_type="email",
                    source_id=msg.id,
                    course_or_sender=extraction.get("course_or_organizer") or extraction.get("course") or msg.sender,
                    title=extraction.get("title") or msg.subject,
                    deadline=deadline,
                    action_required=extraction.get("action_required") or "Review email instructions",
                    is_urgent=bool(
                        deadline
                        and 0 <= (deadline - datetime.now(timezone.utc)).total_seconds() < 21600
                    ),
                    submission_url=None,
                    estimated_hours=float(extraction.get("estimated_hours") or 1.5),
                    confidence=float(extraction.get("confidence") or 0.9),
                    account_source=account_id,
                    has_explicit_deadline=has_explicit_deadline,
                    thread_id=msg.thread_id,
                    canonical_slug=slug
                )
            )

            ledger_entries.append({
                "account_id": account_id,
                "message_id": msg.id,
                "classification": "ACADEMIC_DEADLINE",
                "thread_id": msg.thread_id,
                "internal_date": msg.internal_date,
                "subject": msg.subject,
                "sender": msg.sender,
                "extracted_entity_id": task_id,
                "llm_tokens_spent": 120,
            })

        # One transaction: a ledger row must never claim an email was handled
        # when the extracted task or opportunity was not persisted.
        if new_tasks or new_opps or ledger_entries:
            db.save_ingestion_batch(new_tasks, new_opps, ledger_entries)

        return db.get_all_tasks()

triage_agent = AcademicTriageAgent()
