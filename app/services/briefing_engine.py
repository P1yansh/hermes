from datetime import datetime, timezone
from typing import Optional
from app.models.radar import RadarReport, DailyBriefing, UrgencyTier
from app.services.gemma_client import gemma_client

class BriefingEngine:
    @staticmethod
    async def build_briefing(radar_report: RadarReport, top_opportunity: Optional[dict] = None) -> DailyBriefing:
        critical_items = [
            {"title": i.title, "source": i.source, "hours_left": i.hours_remaining}
            for i in radar_report.items if i.urgency == UrgencyTier.CRITICAL_PANIC
        ]
        approaching_items = [
            {"title": i.title, "source": i.source, "hours_left": i.hours_remaining}
            for i in radar_report.items if i.urgency == UrgencyTier.APPROACHING
        ]

        # Generate speech script
        script = await gemma_client.generate_briefing_script(
            panic_items=critical_items,
            imminent_items=approaching_items,
            top_opp=top_opportunity
        )

        headline = (
            f"🚨 {len(critical_items)} Critical Cutoff(s) Due in <6 Hours!"
            if critical_items else
            (f"⚠️ {len(approaching_items)} Task(s) Due Within 24 Hours" if approaching_items else "🟢 All Clear: Nothing urgent, relax.")
        )

        return DailyBriefing(
            timestamp=datetime.now(timezone.utc),
            headline=headline,
            script=script,
            audio_available=False,
            audio_url=None,
            items_covered=len(critical_items) + len(approaching_items)
        )

briefing_engine = BriefingEngine()
