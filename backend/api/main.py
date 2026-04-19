"""
FastAPI application — entry point.
Initialises DB, agents, task queue, and mounts all routers.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

# Ensure environment is loaded BEFORE any langchain/langsmith imports occur
load_dotenv(override=True)

import asyncio
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
    """Startup: initialise DB, agents, and task queue. Shutdown: cleanup."""
    settings = Settings()

    # 0. Initialize Tracing
    from observability.tracing import init_langsmith_tracing
    init_langsmith_tracing()

    # 1. Ensure database is ready
    from integrations.data_warehouse.sqlite_client import init_db

    init_db(seed=True)
    logger.info("✓ Database ready.")

    # 2. Initialise all agents
    from backend.services.agent_registry import initialise_agents

    initialise_agents(settings)
    logger.info("✓ Agents registered.")

    # 3. Start task queue processor (background worker)
    from backend.services.task_queue import get_task_queue

    queue = get_task_queue()
    task_queue_worker = asyncio.create_task(queue.process_queue())
    logger.info("✓ Task queue started with %d workers.", queue.max_workers)

    # 4. Register WebSocket callback for task completion
    from backend.websocket.manager import get_websocket_manager

    ws_manager = get_websocket_manager()

    async def on_task_complete(task):
        """Called when a task completes (success or failure)."""
        if task.session_id:
            if task.status.value == "completed":
                await ws_manager.broadcast_task_completed(
                    session_id=task.session_id,
                    task_id=task.task_id,
                    agent_name=task.agent_name,
                    action=task.action,
                    result=task.result or {},
                    summary=task.result.get("summary") if task.result else None,
                )
            elif task.status.value == "failed":
                await ws_manager.broadcast_error(
                    error=task.error or "Task failed",
                    agent_name=task.agent_name,
                    session_id=task.session_id,
                    recoverable=(task.retry_count < task.max_retries),
                )

    queue.register_callback(on_task_complete)
    logger.info("✓ WebSocket callbacks registered.")

    yield

    # Cleanup
    logger.info("Shutting down PilotH API...")
    task_queue_worker.cancel()
    logger.info("✓ Task queue stopped.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PilotH — Multi-Agent AI Orchestration Platform",
        description=(
            "Production-grade multi-agent system for enterprise workflow automation. "
            "Supports Vendor Management, Insights, Compliance, and Executive Decision Support. "
            "Features: Real-time WebSockets, Async Task Queue, PII Sanitization, Human-in-the-Loop."
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
    from backend.api.routes.websocket_routes import router as websocket_router
    from backend.api.routes.knowledge_base_routes import router as kb_router
    from backend.api.routes.reports_simulations_routes import router as reports_sim_router
    from backend.api.routes.discovery_routes import router as discovery_router

    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(discovery_router, prefix="/api/v1", tags=["A2A Discovery"])
    app.include_router(agent_router, prefix="/agents", tags=["Agents"])
    app.include_router(vendor_router, prefix="/vendors", tags=["Vendor Management"])
    app.include_router(hitl_router, prefix="/hitl", tags=["Human-in-the-Loop"])
    app.include_router(kb_router, prefix="/kb", tags=["Knowledge Base"])
    app.include_router(reports_sim_router, prefix="/reports", tags=["Reports & Simulations"])
    app.include_router(websocket_router, tags=["WebSocket"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=True)
