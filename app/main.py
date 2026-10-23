import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import db
from app.routers import triage, scout, radar, briefing, sync, telemetry
from app.services.sync_service import sync_service

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


async def _initial_sync():
    try:
        await sync_service.sync_all()
    except Exception as exc:
        logger.warning("Initial sync failed; dashboard will retry on demand: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite schema, then ingest without blocking the first request.
    db.init_db()
    task = asyncio.create_task(_initial_sync())
    app.state.initial_sync_task = task
    try:
        yield
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    description=(
        "🏛️ **Hermes: Autonomous Academic Triage & Opportunity Radar**\n\n"
        "An autonomous agent layer for the Athena AI Workspace, built for Hacktoberfest 2026 Week 3.\n"
        "- **Decoupled Ingestion**: Background sync worker and SQLite persistence so dashboard reads do not wait on LLM inference.\n"
        "- **Stage-1 Pre-Filter**: Instant spam/promotions drop before local LLM inference.\n"
        "- **Academic Triage**: Extracts actionable deadlines from Google Classroom and email inboxes.\n"
        "- **Opportunity Scout**: Discovers relevant hackathons, internships, and grants matching your developer profile.\n"
        "- **Urgency Radar**: Consolidates deadlines into Panic (<6h), Approaching (6-24h), and Chill (>24h) bands.\n"
        "- **ElevenLabs Audio**: Content-addressable cached voice briefing with a browser speech fallback when synthesis is unavailable."
    ),
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware. Browsers reject wildcard origins with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Register Routers
app.include_router(sync.router)
app.include_router(triage.router)
app.include_router(scout.router)
app.include_router(radar.router)
app.include_router(briefing.router)
app.include_router(telemetry.router)

@app.get("/", tags=["UI & Health"])
async def root(request: Request):
    """
    If requested by a browser (Accept: text/html), serves the embedded dashboard UI.
    Otherwise returns system metadata JSON for API consumers and test suites.
    """
    accept = request.headers.get("accept", "")
    index_file = STATIC_DIR / "index.html"
    if "text/html" in accept and index_file.exists():
        return FileResponse(index_file)

    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "run_mode": settings.RUN_MODE,
        "data_source": settings.DATA_SOURCE,
        "timezone": settings.USER_TIMEZONE,
        "local_llm_url": settings.LOCAL_LLM_URL,
        "local_llm_model": settings.LOCAL_LLM_MODEL,
        "audio_provider": "ElevenLabs",
        "docs": "/docs"
    }

@app.get("/health", tags=["UI & Health"])
@app.get("/api/health", tags=["UI & Health"])
async def health_check():
    return {"status": "healthy"}
