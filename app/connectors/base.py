from abc import ABC, abstractmethod
from app.models.academic import EmailMessage, ClassroomCourse
from app.models.opportunity import OpportunityItem

class BaseConnector(ABC):
    @abstractmethod
    async def get_recent_emails(self, max_results: int = 10) -> list[EmailMessage]:
        """Fetch recent emails from inbox"""
        pass

    @abstractmethod
    async def get_classroom_courses(self) -> list[ClassroomCourse]:
        """Fetch enrolled classroom courses and pending coursework"""
        pass

    @abstractmethod
    async def get_opportunities(self) -> list[OpportunityItem]:
        """Fetch hackathons, internships, and grants"""
        pass
