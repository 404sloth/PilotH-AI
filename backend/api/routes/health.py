"""Health check router."""

from fastapi import APIRouter
from pydantic import BaseModel
import sqlite3
import os

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str = "1.0.0"


@router.get("", response_model=HealthResponse, summary="Health check")
def health_check():
    """Returns system health status including database connectivity."""
    from integrations.data_warehouse.sqlite_client import DB_PATH, get_db_connection
    db_status = "ok"
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        db_status = f"error: {e}"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
    )
