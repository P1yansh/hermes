from typing import Literal, Optional

from pydantic import BaseModel

ExtractionCategory = Literal[
    "ACADEMIC_DEADLINE",
    "OPPORTUNITY_DEADLINE",
    "INFORMATIONAL_ALERT",
    "SPAM_NOISE",
]


class EmailExtraction(BaseModel):
    """Validated shape of the Gemma triage response."""

    category: ExtractionCategory = "ACADEMIC_DEADLINE"
    has_explicit_deadline: bool = False
    confidence: float = 0.0
    title: str = ""
    course_or_organizer: str = ""
    exact_deadline_iso: Optional[str] = None
    deadline_verbatim: Optional[str] = None
    needs_web_search: bool = False
    search_query: Optional[str] = None
    action_required: str = ""
    estimated_hours: float = 0.0
