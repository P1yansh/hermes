import asyncio

from app.agents.triage_agent import triage_agent
from app.agents.scout_agent import scout_agent
from app.db import db
from app.services.briefing_engine import briefing_engine
from app.services.elevenlabs import elevenlabs_service
from app.services.radar_engine import radar_engine

sync_lock = asyncio.Lock()


class SyncService:
    @staticmethod
    async def sync_all(force: bool = False) -> dict:
        # Startup sync, the dashboard button, and on-demand endpoint reads can
        # overlap. Serialize them so the same email is not sent to Gemma twice.
        async with sync_lock:
            return await SyncService._sync_all(force=force)

    @staticmethod
    async def _sync_all(force: bool = False) -> dict:
        """
        Runs ingestion and AI extraction in the background:
        1. Checks new items from connectors against SQLite seen_ids.
        2. Runs Stage-1 pre-filter and Gemma 3 on new items only.
        3. Saves extracted tasks and scored opportunities to SQLite.
        4. Compiles the Urgency Radar and caches the daily morning briefing.
        """
        # Ensure DB tables exist
        db.init_db()

        # 1. Ingest & triage academic assignments/emails
        await triage_agent.triage(force_refresh=force)

        # 2. Ingest & score opportunities
        await scout_agent.scout(force_refresh=force)

        # 3. Compile the radar from the committed state. This keeps the sync
        # response identical to a later GET /api/radar call.
        tasks = db.get_all_tasks()
        opportunities = [o for o in db.get_all_opportunities() if o.eligible]

        raw_items: list[dict] = []
        for t in tasks:
            raw_items.append({
                "id": f"academic_{t.source_id}",
                "kind": "academic_assignment",
                "title": t.title,
                "source": t.course_or_sender,
                "deadline": t.deadline,
                "has_explicit_deadline": t.has_explicit_deadline,
                "action_url": t.submission_url,
                "account_source": t.account_source,
                "note": t.action_required
            })

        for o in opportunities:
            raw_items.append({
                "id": f"opp_{o.id}",
                "kind": "hackathon_deadline",
                "title": f"Registration: {o.title}",
                "source": o.organizer,
                "deadline": o.deadline,
                "has_explicit_deadline": o.has_explicit_deadline,
                "action_url": o.url,
                "account_source": o.source_inbox,
                "note": f"{o.type.capitalize()} • {o.eligibility_reason or o.mode or 'Online'}"
            })

        radar_report = radar_engine.compile_radar(raw_items)

        # 4. Generate & cache daily briefing script and audio hash
        top_opp = opportunities[0].model_dump() if opportunities else None
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
            "opportunities_count": len(opportunities),
            "radar_total": radar_report.summary.total_active,
            "watchlist_count": radar_report.summary.watchlist_count,
            "critical_panic_count": radar_report.summary.critical_panic_count,
            "approaching_count": radar_report.summary.approaching_count,
            "chill_count": radar_report.summary.chill_count
        }

sync_service = SyncService()
