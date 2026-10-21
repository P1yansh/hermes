from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import triage, scout, radar, briefing

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "🏛️ **Hermes: Autonomous Academic Triage & Opportunity Radar**\n\n"
        "An autonomous agent layer for the Athena AI Workspace, built for Hacktoberfest 2026 Week 3.\n"
        "- **Academic Triage**: Filters noise and extracts actionable deadlines from Google Classroom and email inboxes.\n"
        "- **Opportunity Scout**: Discovers relevant hackathons, internships, and grants matching your developer profile.\n"
        "- **Urgency Radar**: Consolidates deadlines into Panic (<24h), Imminent (1-3d), and Upcoming bands.\n"
        "- **ElevenLabs Audio**: Synthesizes a daily spoken briefing so you never miss a cutoff."
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
        "data_source": settings.DATA_SOURCE,
        "local_llm_url": settings.LOCAL_LLM_URL,
        "local_llm_model": settings.LOCAL_LLM_MODEL,
        "audio_provider": "ElevenLabs",
        "docs": "/docs"
    }

@app.get("/health", tags=["Health & Status"])
async def health_check():
    return {"status": "healthy"}
