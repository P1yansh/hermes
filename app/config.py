import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings(BaseModel):
    # App
    PROJECT_NAME: str = "Athena Hermes"
    VERSION: str = "0.1.0"
    ENV: str = os.getenv("ENV", "development")
    DATA_SOURCE: str = os.getenv("DATA_SOURCE", "mock").lower()

    # Athena Local Inference (llama-server running Gemma 2)
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8080/v1")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "gemma-2-9b-it")
    LOCAL_LLM_API_KEY: str = os.getenv("LOCAL_LLM_API_KEY", "sk-athena-local")

    # ElevenLabs Audio
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") # Rachel

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
