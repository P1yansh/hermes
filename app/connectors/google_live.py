import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.connectors.base import BaseConnector
from app.connectors.mock_loader import MockConnector
from app.models.academic import EmailMessage, ClassroomCourse, ClassroomAssignment
from app.models.opportunity import OpportunityItem

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]
CLASSROOM_SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
]

class GoogleLiveConnector(BaseConnector):
    """
    Multi-Account Google Workspace Connector.
    Supports authenticating multiple inboxes (e.g., college + 2 personal dev emails)
    under a single Google Cloud Project credentials.json, isolating scopes per account.
    """
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
        accounts_config_path: Optional[str] = None,
    ):
        self.credentials_path = Path(credentials_path or settings.GOOGLE_CREDENTIALS_PATH)
        self.accounts_config_path = Path(accounts_config_path or settings.ACCOUNTS_CONFIG_PATH)
        self.default_token_path = Path(token_path or settings.GOOGLE_TOKEN_PATH)
        self._fallback = MockConnector()
        self.accounts = self._load_accounts()

    def _load_accounts(self) -> list[dict]:
        if self.accounts_config_path.exists():
            try:
                with open(self.accounts_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception as e:
                logger.warning(f"Failed to parse accounts config at {self.accounts_config_path}: {e}")

        # Fallback single account
        return [
            {
                "id": "primary",
                "label": "Primary Google Account",
                "token_file": str(self.default_token_path),
                "enable_gmail": True,
                "enable_classroom": True,
            }
        ]

    def _get_scopes_for_account(self, account: dict) -> list[str]:
        scopes = list(GMAIL_SCOPES)
        if account.get("enable_classroom", False):
            scopes.extend(CLASSROOM_SCOPES)
        return scopes

    def _get_credentials_for_account(self, account: dict):
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request

            token_path = Path(account.get("token_file", self.default_token_path))
            scopes = self._get_scopes_for_account(account)

            creds = None
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), scopes)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif self.credentials_path.exists():
                    token_path.parent.mkdir(parents=True, exist_ok=True)
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), scopes)
                    creds = flow.run_local_server(port=0)
                    with open(token_path, "w", encoding="utf-8") as token_file:
                        token_file.write(creds.to_json())
            return creds
        except Exception as e:
            logger.debug(f"Could not load Google credentials for account {account.get('id')}: {e}")
            return None

    def _get_services(self, account: dict):
        creds = self._get_credentials_for_account(account)
        if not creds:
            return None, None
        try:
            from googleapiclient.discovery import build
            gmail_service = build("gmail", "v1", credentials=creds) if account.get("enable_gmail") else None
            classroom_service = build("classroom", "v1", credentials=creds) if account.get("enable_classroom") else None
            return gmail_service, classroom_service
        except Exception as e:
            logger.warning(f"Error building Google API services for {account.get('id')}: {e}")
            return None, None

    async def get_recent_emails(self, max_results: int = 15) -> list[EmailMessage]:
        all_emails: list[EmailMessage] = []
        any_success = False

        for account in self.accounts:
            if not account.get("enable_gmail", True):
                continue

            acc_id = account.get("id", "primary")
            gmail_service, _ = self._get_services(account)
            if not gmail_service:
                continue

            try:
                results = gmail_service.users().messages().list(
                    userId="me", maxResults=max_results, q="is:unread"
                ).execute()
                messages = results.get("messages", [])

                for m in messages:
                    msg = gmail_service.users().messages().get(userId="me", id=m["id"]).execute()
                    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                    sender = headers.get("from", "Unknown")
                    subject = headers.get("subject", "No Subject")
                    snippet = msg.get("snippet", "")

                    internal_date = int(msg.get("internalDate", 0)) / 1000.0
                    received_at = datetime.fromtimestamp(internal_date, tz=timezone.utc) if internal_date else datetime.now(timezone.utc)

                    all_emails.append(
                        EmailMessage(
                            id=f"{acc_id}:{m['id']}",
                            sender=sender,
                            subject=subject,
                            received_at=received_at,
                            body=snippet,
                            category="academic" if any(w in (subject + snippet).lower() for w in ["assignment", "quiz", "due", "exam", "lab"]) else "general",
                            account_source=acc_id
                        )
                    )
                any_success = True
            except Exception as e:
                logger.warning(f"Failed to fetch emails for account {acc_id}: {e}")

        if any_success and all_emails:
            return all_emails

        # Fallback to Mock if live accounts have no valid credentials yet
        return await self._fallback.get_recent_emails(max_results)

    async def get_classroom_courses(self) -> list[ClassroomCourse]:
        all_courses: list[ClassroomCourse] = []
        any_success = False

        for account in self.accounts:
            if not account.get("enable_classroom", False):
                continue

            acc_id = account.get("id", "primary")
            _, classroom_service = self._get_services(account)
            if not classroom_service:
                continue

            try:
                courses_res = classroom_service.courses().list(pageSize=10).execute()
                courses_raw = courses_res.get("courses", [])

                for c in courses_raw:
                    course_id = c["id"]
                    course_name = c["name"]

                    cw_res = classroom_service.courses().courseWork().list(courseId=course_id).execute()
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
                                id=f"{acc_id}:{cw['id']}",
                                course_name=course_name,
                                title=cw.get("title", "Assignment"),
                                description=cw.get("description", ""),
                                due_at=due_at,
                                max_points=cw.get("maxPoints", 100),
                                submission_url=cw.get("alternateLink"),
                                status="pending",
                                account_source=acc_id
                            )
                        )

                    all_courses.append(
                        ClassroomCourse(
                            id=f"{acc_id}:{course_id}",
                            name=course_name,
                            section=c.get("section"),
                            assignments=assignments,
                            account_source=acc_id
                        )
                    )
                any_success = True
            except Exception as e:
                logger.warning(f"Failed to fetch classroom courses for account {acc_id}: {e}")

        if any_success and all_courses:
            return all_courses

        return await self._fallback.get_classroom_courses()

    async def get_opportunities(self) -> list[OpportunityItem]:
        return await self._fallback.get_opportunities()

MultiAccountGoogleConnector = GoogleLiveConnector
