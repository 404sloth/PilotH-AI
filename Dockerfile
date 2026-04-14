# ─────────────────────────────────────────────────────────────────────────────
# PilotH Dockerfile
# Multi-stage build: builder (deps) → runtime (slim)
# Python 3.13 · uv package manager · non-root user
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.13-slim AS builder

# Install uv (fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy only dependency files first (better layer caching)
COPY requirements.txt pyproject.toml ./

# Create venv and install all dependencies
RUN uv venv .venv && \
    uv pip install --no-cache -r requirements.txt

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r piloth && useradd -r -g piloth -d /app piloth

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv .venv

# Copy application source
COPY --chown=piloth:piloth . .

# Remove dev-only files from image
RUN rm -rf .venv/lib/python3.13/site-packages/pytest* \
           tests/ \
           Scripts/

# Activate venv in PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create data directory for SQLite persistence
RUN mkdir -p /data && chown piloth:piloth /data
ENV SQLITE_DB_PATH="/data/pilot_db.sqlite"

# Switch to non-root user
USER piloth

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose API port
EXPOSE 8000

# Seed DB on startup, then launch uvicorn
CMD ["sh", "-c", \
     "python Scripts/seed_data.py && \
      uvicorn backend.api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 2 \
        --log-level info"]
