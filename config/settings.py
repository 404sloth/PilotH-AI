"""
Settings — centralised configuration with environment variable support.
All sensitive values come from environment or .env file. No defaults for secrets.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── LLM Provider selection ──────────────────────────────
    # "openai" | "groq" | "ollama"
    # Auto-selects based on available API keys if not set.
    llm_primary: str = Field("ollama", description="Primary LLM provider")

    # ── OpenAI ─────────────────────────────────────────────
    openai_api_key: str = Field("", description="OpenAI API key")
    openai_model: str = Field("gpt-4o", description="OpenAI model name")

    # ── Groq (fast inference) ───────────────────────────────
    groq_api_key: str = Field("", description="Groq API key")
    groq_model: str = Field("llama-3.1-8b-instant", description="Groq model")

    # ── Ollama (local fallback) ─────────────────────────────
    ollama_base_url: str = Field(
        "http://localhost:11434", description="Ollama server URL"
    )
    ollama_model: str = Field("llama3", description="Ollama model name")

    # ── Database ────────────────────────────────────────────
    sqlite_db_path: str = Field(
        "pilot_db.sqlite", description="SQLite database file path"
    )

    # ── Human-in-the-Loop ───────────────────────────────────
    hitl_threshold: float = Field(
        0.7, description="Risk score threshold triggering HITL"
    )

    # ── Observability ───────────────────────────────────────
    langsmith_api_key: str = Field("", description="LangSmith tracing API key")
    langsmith_project: str = Field(
        "piloth-vendor", description="LangSmith project name"
    )
    langsmith_tracing_v2: bool = Field(False, description="Enable LangSmith tracing")

    # ── Server ──────────────────────────────────────────────
    host: str = Field("0.0.0.0")
    port: int = Field(8000)
    debug: bool = Field(False)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
