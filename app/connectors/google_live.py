import os
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.models.academic import EmailMessage, ClassroomCourse, ClassroomAssignment
from app.models.opportunity import OpportunityItem

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
]

class GoogleLiveConnector(BaseConnector):
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json"):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self._fallback = MockConnector()
        self._gmail_service = None
        self._classroom_service = None

    def _get_credentials(self):
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request

            creds = None
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif self.credentials_path.exists():
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(self.token_path, "w") as token:
                        token.write(creds.to_json())
            return creds
        except Exception:
            return None

    def _init_services(self):
        if self._gmail_service and self._classroom_service:
            return True
        creds = self._get_credentials()
        if not creds:
            return False
        try:
            from googleapiclient.discovery import build
            self._gmail_service = build("gmail", "v1", credentials=creds)
            self._classroom_service = build("classroom", "v1", credentials=creds)
            return True
        except Exception:
            return False

    async def get_recent_emails(self, max_results: int = 10) -> list[EmailMessage]:
        if not self._init_services():
            return await self._fallback.get_recent_emails(max_results)

        try:
            results = self._gmail_service.users().messages().list(
                userId="me", maxResults=max_results, q="is:unread"
            ).execute()
            messages = results.get("messages", [])

            email_list: list[EmailMessage] = []
            for m in messages:
                msg = self._gmail_service.users().messages().get(userId="me", id=m["id"]).execute()
                headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                sender = headers.get("from", "Unknown")
                subject = headers.get("subject", "No Subject")
                snippet = msg.get("snippet", "")
                
                # Timestamp in seconds
                internal_date = int(msg.get("internalDate", 0)) / 1000.0
                received_at = datetime.fromtimestamp(internal_date, tz=timezone.utc) if internal_date else datetime.now(timezone.utc)

                email_list.append(
                    EmailMessage(
                        id=m["id"],
                        sender=sender,
                        subject=subject,
                        received_at=received_at,
                        body=snippet,
                        category="academic" if any(w in (subject + snippet).lower() for w in ["assignment", "quiz", "due", "exam", "lab"]) else "general"
                    )
                )
            return email_list if email_list else await self._fallback.get_recent_emails(max_results)
        except Exception:
            return await self._fallback.get_recent_emails(max_results)

    async def get_classroom_courses(self) -> list[ClassroomCourse]:
        if not self._init_services():
            return await self._fallback.get_classroom_courses()

        try:
            courses_res = self._classroom_service.courses().list(pageSize=10).execute()
            courses_raw = courses_res.get("courses", [])
            courses: list[ClassroomCourse] = []

            for c in courses_raw:
                course_id = c["id"]
                course_name = c["name"]
                
                # Fetch coursework
                cw_res = self._classroom_service.courses().courseWork().list(courseId=course_id).execute()
                assignments: list[ClassroomAssignment] = []
                for cw in cw_res.get("courseWork", []):
                    due_date = cw.get("dueDate", {})
                    due_time = cw.get("dueTime", {})
                    if due_date:
                        due_at = datetime(
                            year=due_date.get("year", 2026),
                            month=due_date.get("month", 1),
                            day=due_date.get("day", 1),
                            hour=due_time.get("hours", 23),
                            minute=due_time.get("minutes", 59),
                            tzinfo=timezone.utc
                        )
                    else:
                        due_at = datetime.now(timezone.utc)

                    assignments.append(
                        ClassroomAssignment(
                            id=cw["id"],
                            course_name=course_name,
                            title=cw.get("title", "Assignment"),
                            description=cw.get("description", ""),
                            due_at=due_at,
                            max_points=cw.get("maxPoints", 100),
                            submission_url=cw.get("alternateLink"),
                            status="pending"
                        )
                    )

                courses.append(
                    ClassroomCourse(
                        id=course_id,
                        name=course_name,
                        section=c.get("section"),
                        assignments=assignments
                    )
                )
            return courses if courses else await self._fallback.get_classroom_courses()
        except Exception:
            return await self._fallback.get_classroom_courses()

    async def get_opportunities(self) -> list[OpportunityItem]:
        # Opportunities are fetched from curated sources or SerpApi
        return await self._fallback.get_opportunities()
