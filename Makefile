.PHONY: help setup install test test-vendor test-meetings test-all clean run run-dev run-test healthcheck db-init db-reset lint format

help:
	@echo "PilotH — Multi-Agent AI Orchestration Platform"
	@echo ""
	@echo "Quick Commands:"
	@echo "  make setup          - Initial setup (venv + install + db)"
	@echo "  make run            - Start API server (production)"
	@echo "  make run-dev        - Start API server (with reload)"
	@echo "  make test           - Run all tests"
	@echo "  make test-vendor    - Vendor Management tests only"
	@echo "  make test-meetings  - Communication Agent tests only"
	@echo "  make healthcheck    - Check API and LLM status"
	@echo "  make db-init        - Initialize and seed database"
	@echo "  make db-reset       - Delete database (DANGEROUS)"
	@echo "  make clean          - Clean temporary files"
	@echo "  make lint           - Run code linting"
	@echo ""

setup: install db-init
	@echo "✅ Setup complete! Run: make run-dev"

install:
	@echo "📦 Installing dependencies..."
	@test -d .venv || python3 -m venv .venv
	@. .venv/bin/activate && pip install -q -r requirements.txt
	@test -f .env || cp config/.env.example .env
	@echo "✅ Dependencies installed"

test: test-all

test-all: db-init
	@echo "🧪 Running all tests..."
	@. .venv/bin/activate && python3 tests/test_vendor_management.py && \
	  python3 tests/test_meetings_agent.py
	@echo "✅ All tests passed"

test-vendor: db-init
	@echo "🧪 Running Vendor Management tests..."
	@. .venv/bin/activate && python3 tests/test_vendor_management.py

test-meetings: db-init
	@echo "🧪 Running Communication Agent tests..."
	@. .venv/bin/activate && python3 tests/test_meetings_agent.py

run:
	@echo "🚀 Starting API server (production)..."
	@. .venv/bin/activate && uvicorn backend.api.main:app --host 0.0.0.0 --port 8000

run-dev:
	@echo "🚀 Starting API server (development with reload)..."
	@. .venv/bin/activate && uvicorn backend.api.main:app --reload --port 8000

run-test:
	@echo "🚀 Starting test server..."
	@. .venv/bin/activate && uvicorn backend.api.main:app --host 127.0.0.1 --port 9999

healthcheck:
	@echo "🏥 Checking API health..."
	@curl -s http://localhost:8000/health | python3 -m json.tool || echo "❌ API not responding"
	@echo ""
	@echo "🏥 Checking Ollama..."
	@curl -s http://localhost:11434/api/tags | python3 -m json.tool || echo "⚠️  Ollama not running"

db-init:
	@echo "🗄️  Initializing database..."
	@. .venv/bin/activate && python3 << 'EOF'
from integrations.data_warehouse.sqlite_client import init_db
init_db(seed=True)
import sqlite3
conn = sqlite3.connect("pilot_db.sqlite")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(DISTINCT type) FROM sqlite_master WHERE type IN ('table', 'index')")
count = cursor.fetchone()[0]
print(f"✅ Database ready ({count} objects)")
EOF

db-reset:
	@echo "⚠️  WARNING: This will delete all data!"
	@read -p "Are you sure? (y/N) " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
	  rm -f pilot_db.sqlite; \
	  echo "✅ Database deleted"; \
	else \
	  echo "Cancelled"; \
	fi

db-query:
	@echo "Opening SQLite shell..."
	@sqlite3 pilot_db.sqlite

clean:
	@echo "🧹 Cleaning temporary files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -f .pytest_cache .coverage htmlcov
	@echo "✅ Cleaned"

lint:
	@echo "🔍 Linting Python code..."
	@. .venv/bin/activate && python3 -m pylint agents/ backend/ orchestrator/ --disable=all --enable=E,F 2>/dev/null || echo "Install pylint: pip install pylint"

format:
	@echo "🎨 Formatting code..."
	@. .venv/bin/activate && python3 -m black . --line-length 100 --quiet 2>/dev/null || echo "Install black: pip install black"

# Docker commands (optional)
docker-build:
	docker build -t piloth:latest .

docker-run:
	docker-compose up

# Advanced
shell:
	@. .venv/bin/activate && python3

db-shell:
	@sqlite3 pilot_db.sqlite

logs:
	@tail -f /tmp/piloth.log

lint-fix:
	@. .venv/bin/activate && python3 -m black . --line-length 100 2>/dev/null
	@. .venv/bin/activate && python3 -m isort . 2>/dev/null || true

test-coverage:
	@. .venv/bin/activate && python3 -m pytest tests/ --cov --cov-report=html

demo:
	@echo "🎬 Running interactive demo..."
	@. .venv/bin/activate && python3 << 'EOF'
import sys
from integrations.data_warehouse.sqlite_client import init_db
from backend.services.agent_registry import initialise_agents
from config.settings import Settings
from orchestrator.controller import OrchestratorController

init_db()
settings = Settings()
initialise_agents(settings)
controller = OrchestratorController(settings)

# Example request
result = controller.handle(
    message="Find the best cloud infrastructure vendors for $100k budget",
    session_id="demo-session"
)

print(f"\n✅ Demo complete!")
print(f"   Agent: {result['intent']['agent']}")
print(f"   Action: {result['intent']['action']}")
print(f"   Status: {result['result'].get('status')}")
EOF
