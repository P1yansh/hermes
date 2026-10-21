from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field

class UrgencyTier(str, Enum):
    PANIC = "panic"         # < 24 hours
    IMMINENT = "imminent"   # 24h - 72h (1 - 3 days)
    UPCOMING = "upcoming"   # > 72h (3+ days)
    PASSED = "passed"       # Deadline passed

class RadarItem(BaseModel):
    id: str
    kind: Literal["academic_assignment", "hackathon_deadline", "exam_warning"]
    title: str
    source: str
    deadline: datetime
    hours_remaining: float
    urgency: UrgencyTier
    action_url: Optional[str] = None
    priority_weight: float = 1.0  # higher = more critical

class RadarSummary(BaseModel):
    panic_count: int = 0
    imminent_count: int = 0
    upcoming_count: int = 0
    total_active: int = 0

class RadarReport(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: RadarSummary
    items: list[RadarItem]

class DailyBriefing(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    headline: str
    script: str
    audio_available: bool = False
    audio_url: Optional[str] = None
    items_covered: int = 0
