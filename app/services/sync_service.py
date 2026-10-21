from app.agents.triage_agent import triage_agent
from app.agents.scout_agent import scout_agent
from app.db import db
from app.services.briefing_engine import briefing_engine
from app.services.elevenlabs import elevenlabs_service
from app.services.radar_engine import radar_engine

class SyncService:
    @staticmethod
    async def sync_all(force: bool = False) -> dict:
        """
        Runs ingestion and AI extraction in the background:
        1. Checks new items from connectors against SQLite seen_ids.
        2. Runs Stage-1 pre-filter and Gemma 2 on new items only.
        3. Saves extracted tasks and scored opportunities to SQLite.
        4. Compiles the Urgency Radar and caches the daily morning briefing.
        """
        # Ensure DB tables exist
        db.init_db()

        # 1. Ingest & triage academic assignments/emails
        tasks = await triage_agent.triage(force_refresh=force)

        # 2. Ingest & score opportunities
        scout_report = await scout_agent.scout(force_refresh=force)

        # 3. Compile radar from persistent state
        raw_items: list[dict] = []
        for t in tasks:
            if t.deadline:
                raw_items.append({
                    "id": f"academic_{t.source_id}",
                    "kind": "academic_assignment",
                    "title": t.title,
                    "source": t.course_or_sender,
                    "deadline": t.deadline,
                    "action_url": t.submission_url
                })

        for o in scout_report.matches:
            raw_items.append({
                "id": f"opp_{o.id}",
                "kind": "hackathon_deadline",
                "title": f"Registration: {o.title}",
                "source": o.organizer,
                "deadline": o.deadline,
                "action_url": o.url
            })

        radar_report = radar_engine.compile_radar(raw_items)

        # 4. Generate & cache daily briefing script and audio hash
        top_opp = scout_report.matches[0].model_dump() if scout_report.matches else None
        briefing = await briefing_engine.build_briefing(radar_report, top_opportunity=top_opp)
        audio_hash = elevenlabs_service.get_content_hash(briefing.script)

        db.save_briefing(
            headline=briefing.headline,
            script=briefing.script,
            audio_hash=audio_hash,
            items_covered=briefing.items_covered
        )

        return {
            "status": "synced",
            "tasks_count": len(tasks),
            "opportunities_count": len(scout_report.matches),
            "radar_total": radar_report.summary.total_active,
            "panic_count": radar_report.summary.panic_count
        }

sync_service = SyncService()
