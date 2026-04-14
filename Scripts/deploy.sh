#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — PilotH deployment script
#
# Usage:
#   ./Scripts/deploy.sh                    # local dev server
#   ./Scripts/deploy.sh --docker           # docker-compose up
#   ./Scripts/deploy.sh --prod             # production (gunicorn)
#   ./Scripts/deploy.sh --seed             # seed DB then start
#   ./Scripts/deploy.sh --test             # run all tests then exit
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_ROOT/.venv/bin/python3"
UVICORN="$PROJECT_ROOT/.venv/bin/uvicorn"
GUNICORN="$PROJECT_ROOT/.venv/bin/gunicorn"

# Defaults
MODE="dev"
SEED=false
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-4}"

# ── Parse args ────────────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --docker)  MODE="docker" ;;
    --prod)    MODE="prod"   ;;
    --seed)    SEED=true     ;;
    --test)    MODE="test"   ;;
    --help)
      echo "Usage: $0 [--docker|--prod|--seed|--test]"
      exit 0
      ;;
  esac
done

cd "$PROJECT_ROOT"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo "  ✓ Loaded .env"
elif [ -f "config/.env.example" ]; then
  echo "  ⚠ No .env found — copy config/.env.example to .env and fill in values."
fi

# ── Pre-flight checks ─────────────────────────────────────────────────────────
echo ""
echo "  PilotH Deployment — mode: $MODE"
echo "  ──────────────────────────────"

if [ ! -f "$VENV" ]; then
  echo "  ✗ Virtual environment not found at .venv"
  echo "    Run: uv venv && uv pip install -r requirements.txt"
  exit 1
fi
echo "  ✓ Virtual environment found"

# ── Seed database ─────────────────────────────────────────────────────────────
if [ "$SEED" = true ] || [ "$MODE" = "test" ]; then
  echo "  → Seeding database..."
  "$VENV" Scripts/seed_data.py --reset
fi

# ── Validate registry ─────────────────────────────────────────────────────────
echo "  → Validating agent registry..."
"$VENV" Scripts/register_agents.py --validate || {
  echo "  ✗ Agent validation failed — fix errors before deploying."
  exit 1
}

echo "  → Validating tool registry..."
"$VENV" Scripts/register_tools.py --validate || {
  echo "  ✗ Tool validation failed — fix errors before deploying."
  exit 1
}

# ── Test mode ─────────────────────────────────────────────────────────────────
if [ "$MODE" = "test" ]; then
  echo ""
  echo "  Running test suites..."
  "$VENV" tests/test_vendor_management.py
  "$VENV" tests/test_meetings_agent.py
  echo "  ✓ All tests passed."
  exit 0
fi

# ── Docker mode ───────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
  echo "  → Starting via docker-compose..."
  docker-compose up --build -d
  echo "  ✓ Containers started. API: http://localhost:$PORT"
  echo "  → Logs: docker-compose logs -f piloth-api"
  exit 0
fi

# ── Production mode (gunicorn) ────────────────────────────────────────────────
if [ "$MODE" = "prod" ]; then
  echo "  → Starting production server (gunicorn)..."
  if [ ! -f "$GUNICORN" ]; then
    echo "  ✗ gunicorn not found. Install: uv pip install gunicorn"
    exit 1
  fi
  exec "$GUNICORN" backend.api.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "$WORKERS" \
    --bind "$HOST:$PORT" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
fi

# ── Dev mode (default) ────────────────────────────────────────────────────────
echo "  → Starting development server..."
echo "  → API: http://localhost:$PORT"
echo "  → Docs: http://localhost:$PORT/docs"
echo ""
exec "$PROJECT_ROOT/.venv/bin/uvicorn" \
  backend.api.main:app \
  --reload \
  --host "$HOST" \
  --port "$PORT" \
  --log-level info
