from datetime import datetime, timezone
from typing import Optional
from app.models.radar import RadarReport, DailyBriefing, UrgencyTier
from app.services.gemma_client import gemma_client

class BriefingEngine:
    @staticmethod
    async def build_briefing(radar_report: RadarReport, top_opportunity: Optional[dict] = None) -> DailyBriefing:
        panic_items = [
            {"title": i.title, "source": i.source, "hours_left": i.hours_remaining}
            for i in radar_report.items if i.urgency == UrgencyTier.PANIC
        ]
        imminent_items = [
            {"title": i.title, "source": i.source, "hours_left": i.hours_remaining}
            for i in radar_report.items if i.urgency == UrgencyTier.IMMINENT
        ]

        # Generate speech script
        script = await gemma_client.generate_briefing_script(
            panic_items=panic_items,
            imminent_items=imminent_items,
            top_opp=top_opportunity
        )

        headline = (
            f"🚨 {len(panic_items)} Critical Deadline(s) Due in <24h"
            if panic_items else
            "🟢 All Clear: Move at your own pace today"
        )

        return DailyBriefing(
            timestamp=datetime.now(timezone.utc),
            headline=headline,
            script=script,
            audio_available=False,
            audio_url=None,
            items_covered=len(panic_items) + len(imminent_items)
        )

briefing_engine = BriefingEngine()
