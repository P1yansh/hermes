from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field

class UrgencyTier(str, Enum):
    CRITICAL_PANIC = "critical_panic"  # < 6h: "jaldi kar alsi, warna gaya bas {x} hours baki hai"
    APPROACHING = "approaching"        # 6h - 24h: "abhi to {x} ghante hai :)"
    CHILL = "chill"                    # > 24h: "abhi kyu karna, {x} days baki hai"
    PASSED = "passed"                  # Passed

class RadarItem(BaseModel):
    id: str
    kind: Literal["academic_assignment", "hackathon_deadline", "exam_warning"]
    title: str
    source: str
    deadline: datetime
    hours_remaining: float
    urgency: UrgencyTier
    sloth_message: str
    action_url: Optional[str] = None
    priority_weight: float = 1.0  # higher = more critical

class RadarSummary(BaseModel):
    critical_panic_count: int = 0
    approaching_count: int = 0
    chill_count: int = 0
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
