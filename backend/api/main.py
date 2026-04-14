"""
FastAPI application — entry point.
Initialises DB, agents, and mounts all routers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import Settings

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise DB and agents. Shutdown: cleanup."""
    settings = Settings()

    # 1. Ensure database is ready
    from integrations.data_warehouse.sqlite_client import init_db

    init_db(seed=True)
    logger.info("Database ready.")

    # 2. Initialise all agents
    from backend.services.agent_registry import initialise_agents

    initialise_agents(settings)

    yield
    logger.info("Shutting down PilotH API.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PilotH — Multi-Agent AI Orchestration Platform",
        description=(
            "Production-grade multi-agent system for enterprise workflow automation. "
            "Supports Vendor Management, Insights, Compliance, and Executive Decision Support."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    from backend.api.routes.health import router as health_router
    from backend.api.routes.agent_routes import router as agent_router
    from backend.api.routes.vendor_routes import router as vendor_router
    from backend.api.routes.human_loop_routes import router as hitl_router

    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(agent_router, prefix="/agents", tags=["Agents"])
    app.include_router(vendor_router, prefix="/vendors", tags=["Vendor Management"])
    app.include_router(hitl_router, prefix="/hitl", tags=["Human-in-the-Loop"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=True)
