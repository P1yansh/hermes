from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import db
from app.routers import triage, scout, radar, briefing, sync
from app.services.sync_service import sync_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    db.init_db()
    # Initial background ingestion and triage sync
    try:
        await sync_service.sync_all()
    except Exception:
        pass
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    description=(
        "🏛️ **Hermes: Autonomous Academic Triage & Opportunity Radar**\n\n"
        "An autonomous agent layer for the Athena AI Workspace, built for Hacktoberfest 2026 Week 3.\n"
        "- **Decoupled Ingestion**: Background sync worker & SQLite persistence for sub-millisecond query responses.\n"
        "- **Stage-1 Pre-Filter**: Instant spam/promotions drop before local LLM inference.\n"
        "- **Academic Triage**: Extracts actionable deadlines from Google Classroom and email inboxes.\n"
        "- **Opportunity Scout**: Discovers relevant hackathons, internships, and grants matching your developer profile.\n"
        "- **Urgency Radar**: Consolidates deadlines into Panic (<24h), Imminent (1-3d), and Upcoming bands.\n"
        "- **ElevenLabs Audio**: Content-addressable cached voice briefing so you never miss a cutoff."
    ),
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(sync.router)
app.include_router(triage.router)
app.include_router(scout.router)
app.include_router(radar.router)
app.include_router(briefing.router)

@app.get("/", tags=["Health & Status"])
async def root():
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

@app.get("/health", tags=["Health & Status"])
async def health_check():
    return {"status": "healthy"}
