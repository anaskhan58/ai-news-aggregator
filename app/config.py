"""Central settings, read once from environment variables (and a local .env file)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _database_url() -> str:
    """DATABASE_URL wins (Render sets it); otherwise build one for the local Docker Postgres."""
    url = os.getenv("DATABASE_URL")
    if not url:
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "postgres")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "ai_news_aggregator")
        url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    # SQLAlchemy needs an explicit driver; Render hands out postgres:// URLs.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = _database_url()

    # LLM: "openai" (Responses API) or "ollama" (local, OpenAI-compatible endpoint)
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai").lower()
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    # Email (Gmail SMTP + app password)
    email_from: str | None = os.getenv("MY_EMAIL")
    email_app_password: str | None = os.getenv("APP_PASSWORD")
    email_to: str | None = os.getenv("EMAIL_TO") or os.getenv("MY_EMAIL")

    # Optional Webshare rotating residential proxy for YouTube transcripts
    webshare_username: str | None = os.getenv("WEBSHARE_USERNAME")
    webshare_password: str | None = os.getenv("WEBSHARE_PASSWORD")

    lookback_hours: int = _int("LOOKBACK_HOURS", 24)
    top_n: int = _int("TOP_N", 10)


settings = Settings()
