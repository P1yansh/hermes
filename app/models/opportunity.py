from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field

OpportunityType = Literal["hackathon", "internship", "grant", "academic_program"]

class OpportunityItem(BaseModel):
    id: str
    title: str
    type: OpportunityType
    organizer: str
    deadline: datetime
    prizes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    description: str
    url: str
    relevance_score: int = 5

class UserProfile(BaseModel):
    name: str = "P1yansh"
    university: str = "Computer Science"
    interests: list[str] = Field(default_factory=lambda: ["AI Agents", "Local LLMs", "Systems", "Open Source"])
    skills: list[str] = Field(default_factory=lambda: ["Python", "C++", "FastAPI", "Linux", "llama.cpp"])
    min_prize_relevance: int = 6

class ScoutReport(BaseModel):
    total_found: int
    matches: list[OpportunityItem]
    scouted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
