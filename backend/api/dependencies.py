"""
FastAPI dependency injectors.
"""

from __future__ import annotations

from config.settings import Settings
from backend.services.agent_registry import get_agent as _get_agent


def get_settings() -> Settings:
    return Settings()


def get_vendor_agent():
    agent = _get_agent("vendor_management")
    if not agent:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail="Vendor Management Agent not ready."
        )
    return agent
