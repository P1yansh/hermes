from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class EmailMessage(BaseModel):
    id: str
    sender: str
    subject: str
    received_at: datetime
    body: str
    category: str = "general"

class ClassroomAssignment(BaseModel):
    id: str
    course_name: str
    title: str
    description: str
    due_at: datetime
    max_points: Optional[int] = 100
    submission_url: Optional[str] = None
    status: str = "pending"

class ClassroomCourse(BaseModel):
    id: str
    name: str
    section: Optional[str] = None
    assignments: list[ClassroomAssignment] = Field(default_factory=list)

class ExtractedTask(BaseModel):
    source_type: str  # "email" or "classroom"
    source_id: str
    course_or_sender: str
    title: str
    deadline: Optional[datetime] = None
    action_required: str
    is_urgent: bool = False
    submission_url: Optional[str] = None
    estimated_hours: Optional[float] = 1.0
    confidence: float = 1.0
