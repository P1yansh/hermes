import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings(BaseModel):
    # App & Runtime Topology
    PROJECT_NAME: str = "Athena Hermes"
    VERSION: str = "0.2.0"
    ENV: str = os.getenv("ENV", "development")
    RUN_MODE: str = os.getenv("RUN_MODE", "local").lower() # "local" (Athena daemon) or "cloud_sandbox" (Render demo)
    DATA_SOURCE: str = os.getenv("DATA_SOURCE", "mock").lower() # "mock" or "live"
    USER_TIMEZONE: str = os.getenv("USER_TIMEZONE", "Asia/Kolkata")

    # Persistence
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "hermes.db"))

    # Multi-Account & Location Profiles
    ACCOUNTS_CONFIG_PATH: str = os.getenv("ACCOUNTS_CONFIG_PATH", str(BASE_DIR / "config" / "accounts.json"))
    TOKENS_DIR: str = os.getenv("TOKENS_DIR", str(BASE_DIR / "tokens"))
    USER_CITY: str = os.getenv("USER_CITY", "lucknow")
    USER_STATE: str = os.getenv("USER_STATE", "uttar pradesh")
    USER_COUNTRY: str = os.getenv("USER_COUNTRY", "india")

    # Athena Local Inference (llama-server running Gemma 3 4B)
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8080/v1")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "gemma-3-4b-it")
    LOCAL_LLM_API_KEY: str = os.getenv("LOCAL_LLM_API_KEY", "sk-athena-local")

    # ElevenLabs Audio
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb") # George (free tier default)

    # Google Live API
    GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    GOOGLE_TOKEN_PATH: str = os.getenv("GOOGLE_TOKEN_PATH", "token.json")

    # SerpApi (Optional)
    SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: list[str] = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",")]

settings = Settings()

def to_utc(dt: datetime) -> datetime:
    """Normalize any naive or local datetime into a timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        try:
            tz = ZoneInfo(settings.USER_TIMEZONE)
            dt = dt.replace(tzinfo=tz)
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
