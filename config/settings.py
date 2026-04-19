"""
Settings — centralised configuration with environment variable support.
All sensitive values come from environment or .env file. No defaults for secrets.
"""

import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)


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
    ollama_model: str = Field("qwen2.5:3b", description="Ollama model name")

    # ── Database ────────────────────────────────────────────
    sqlite_db_path: str = Field(
        "pilot_db.sqlite", description="SQLite database file path"
    )

    # ── Human-in-the-Loop ───────────────────────────────────
    hitl_threshold: float = Field(
        0.7, description="Risk score threshold triggering HITL"
    )

    # ── Observability ───────────────────────────────────────
    langchain_api_key: str = Field("", description="LangSmith tracing API key", validation_alias="langsmith_api_key")
    langchain_project: str = Field("ai-agents-testing", description="LangSmith project name", validation_alias="langsmith_project")
    langchain_tracing_v2: bool = Field(True, description="Enable LangSmith tracing", validation_alias="langsmith_tracing_v2")

    # ── Server ──────────────────────────────────────────────
    host: str = Field("0.0.0.0")
    port: int = Field(8000)
    debug: bool = Field(False)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        """Export LangChain tracing variables to os.environ so the library picks them up."""
        import os
        # If an API key is present, we likely want tracing enabled even if .env says false
        # especially since the user explicitly asked to fix the "no traces" issue.
        enable_tracing = self.langchain_tracing_v2 or bool(self.langchain_api_key)
        
        if enable_tracing and self.langchain_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.langchain_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.langchain_project or "piloth-default"
            os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
            
            # Ensure other crucial keys are also in environ
            if self.openai_api_key:
                os.environ["OPENAI_API_KEY"] = self.openai_api_key
            if self.groq_api_key:
                os.environ["GROQ_API_KEY"] = self.groq_api_key
                
            logger.info("[Observability] LangSmith Tracing enabled for project: %s", os.environ["LANGCHAIN_PROJECT"])
        else:
            logger.info("[Observability] LangSmith Tracing is disabled.")
