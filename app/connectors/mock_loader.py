import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.connectors.base import BaseConnector
from app.models.academic import EmailMessage, ClassroomCourse, ClassroomAssignment
from app.models.opportunity import OpportunityItem

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

class MockConnector(BaseConnector):
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir

    async def get_recent_emails(self, max_results: int = 10) -> list[EmailMessage]:
        file_path = self.data_dir / "mock_emails.json"
        if not file_path.exists():
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        now = datetime.now(timezone.utc)
        emails: list[EmailMessage] = []
        for item in raw_data[:max_results]:
            hours_ago = item.get("received_hours_ago", 1)
            received_at = now - timedelta(hours=hours_ago)
            emails.append(
                EmailMessage(
                    id=item["id"],
                    sender=item["sender"],
                    subject=item["subject"],
                    received_at=received_at,
                    body=item["body"],
                    category=item.get("category", "general"),
                    thread_id=item.get("thread_id", f"mock_th_{item['id']}"),
                    internal_date=int(received_at.timestamp() * 1000)
                )
            )
        return emails

    async def get_classroom_courses(self) -> list[ClassroomCourse]:
        file_path = self.data_dir / "mock_classroom.json"
        if not file_path.exists():
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        now = datetime.now(timezone.utc)
        courses: list[ClassroomCourse] = []
        for c in raw_data:
            course_name = c["course_name"]
            assignments: list[ClassroomAssignment] = []
            for a in c.get("assignments", []):
                due_hours = a.get("due_hours_from_now", 24)
                due_at = now + timedelta(hours=due_hours)
                assignments.append(
                    ClassroomAssignment(
                        id=a["id"],
                        course_name=course_name,
                        title=a["title"],
                        description=a["description"],
                        due_at=due_at,
                        max_points=a.get("max_points", 100),
                        submission_url=a.get("submission_url"),
                        status=a.get("status", "pending")
                    )
                )
            courses.append(
                ClassroomCourse(
                    id=c["course_id"],
                    name=course_name,
                    section=c.get("section"),
                    assignments=assignments
                )
            )
        return courses

    async def get_opportunities(self) -> list[OpportunityItem]:
        file_path = self.data_dir / "mock_opportunities.json"
        if not file_path.exists():
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        now = datetime.now(timezone.utc)
        opportunities: list[OpportunityItem] = []
        for o in raw_data:
            deadline_hours = o.get("deadline_hours_from_now", 72)
            deadline = now + timedelta(hours=deadline_hours)
            opportunities.append(
                OpportunityItem(
                    id=o["id"],
                    title=o["title"],
                    type=o["type"],
                    organizer=o["organizer"],
                    deadline=deadline,
                    prizes=o.get("prizes"),
                    tags=o.get("tags", []),
                    description=o["description"],
                    url=o["url"],
                    relevance_score=o.get("relevance_score", 5)
                )
            )
        return opportunities
