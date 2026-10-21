from datetime import datetime, timezone
from app.config import settings
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.connectors.google_live import GoogleLiveConnector
from app.models.academic import ExtractedTask
from app.services.gemma_client import gemma_client

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

    async def triage(self) -> list[ExtractedTask]:
        """
        Gathers raw inboxes and classroom streams, filtering spam
        and extracting structured deadlines via Gemma.
        """
        tasks: list[ExtractedTask] = []

        # 1. Process Google Classroom assignments
        courses = await self.connector.get_classroom_courses()
        for course in courses:
            for a in course.assignments:
                tasks.append(
                    ExtractedTask(
                        source_type="classroom",
                        source_id=a.id,
                        course_or_sender=course.name,
                        title=a.title,
                        deadline=a.due_at,
                        action_required=f"Submit '{a.title}' on Google Classroom",
                        is_urgent=False,  # Evaluated by RadarEngine
                        submission_url=a.submission_url,
                        estimated_hours=2.5,
                        confidence=1.0
                    )
                )

        # 2. Process emails via Gemma 2 triage
        emails = await self.connector.get_recent_emails(max_results=10)
        for msg in emails:
            extraction = await gemma_client.extract_email_task(
                sender=msg.sender,
                subject=msg.subject,
                body=msg.body
            )

            if extraction.get("has_action") and not extraction.get("is_spam"):
                # Approximate deadline from email or use msg received date + delta
                now = datetime.now(timezone.utc)
                deadline_text = extraction.get("deadline_text", "").lower()
                if "tonight" in deadline_text:
                    approx_deadline = now.replace(hour=23, minute=59, second=0)
                elif "tomorrow" in deadline_text:
                    approx_deadline = now.replace(hour=18, minute=0, second=0)
                else:
                    approx_deadline = now

                tasks.append(
                    ExtractedTask(
                        source_type="email",
                        source_id=msg.id,
                        course_or_sender=extraction.get("course", msg.sender),
                        title=extraction.get("title", msg.subject),
                        deadline=approx_deadline,
                        action_required=extraction.get("action_required", "Check email instructions"),
                        is_urgent=True if "tonight" in deadline_text else False,
                        submission_url=None,
                        estimated_hours=extraction.get("estimated_hours", 1.5),
                        confidence=0.9
                    )
                )

        return tasks

triage_agent = AcademicTriageAgent()
