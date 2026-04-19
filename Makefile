.PHONY: help setup install test test-vendor test-meetings test-all clean run run-dev run-test healthcheck db-init db-reset lint format init-system shell

# Detect OS
ifeq ($(OS),Windows_NT)
    PYTHON = python
    VENV_BIN = .venv\Scripts
    SEP = \\
else
    PYTHON = python3
    VENV_BIN = .venv/bin
    SEP = /
endif

PIP = $(PYTHON) -m pip
ifeq ($(OS),Windows_NT)
    UVICORN = .venv\Scripts\uvicorn
else
    UVICORN = .venv/bin/uvicorn
endif

help:
	@echo PilotH — Multi-AI Agent Orchestration Platform
	@echo.
	@echo Quick Commands:
	@echo   make setup       - Initial setup
	@echo   make run-dev     - Start dev server
	@echo   make run         - Start production server
	@echo   make test        - Run all tests
	@echo   make clean       - Clean temp files
	@echo.

# ----------------------
# SETUP
# ----------------------

setup: install db-init
	@echo Setup complete! Run: make run-dev

install:
	@echo Installing dependencies...
	@$(PYTHON) -c "import os; os.system('python -m venv .venv') if not os.path.exists('.venv') else None"
	@$(PIP) install -r requirements.txt
	@$(PYTHON) -c "import shutil, os; shutil.copy('config/.env.example', '.env') if not os.path.exists('.env') else None"
	@echo Dependencies installed

init-system:
	@echo Initializing system...
	@$(PYTHON) Scripts/init_system.py
	@echo Done

# ----------------------
# RUN
# ----------------------

run:
	@echo Starting production server...
	@$(UVICORN) backend.api.main:app --host 0.0.0.0 --port 8000

run-dev:
	@echo Starting dev server...
	@$(PYTHON) -m dotenv run -- $(UVICORN) backend.api.main:app --reload --port 8000

run-test:
	@echo Starting test server...
	@$(UVICORN) backend.api.main:app --host 127.0.0.1 --port 9999

# ----------------------
# TESTING
# ----------------------

test: test-all

test-all: db-init
	@echo Running all tests...
	@$(PYTHON) tests/test_vendor_management.py
	@$(PYTHON) tests/test_meetings_agent.py
	@echo All tests passed

test-vendor: db-init
	@$(PYTHON) tests/test_vendor_management.py

test-meetings: db-init
	@$(PYTHON) tests/test_meetings_agent.py

# ----------------------
# DATABASE
# ----------------------

db-init:
	@echo Initializing database...
	@$(PYTHON) -c "from integrations.data_warehouse.sqlite_client import init_db; init_db(seed=True)"
	@$(PYTHON) -c "import sqlite3; conn=sqlite3.connect('pilot_db.sqlite'); cur=conn.cursor(); cur.execute('SELECT COUNT(*) FROM sqlite_master'); print('Database ready:', cur.fetchone()[0])"

db-reset:
	@$(PYTHON) -c "import os; c=input('Delete DB? (y/N): '); \
print('Deleted') if c.lower()=='y' and (os.remove('pilot_db.sqlite') if os.path.exists('pilot_db.sqlite') else True) else print('Cancelled')"

db-shell:
	@$(PYTHON) -c "import sqlite3; conn=sqlite3.connect('pilot_db.sqlite'); print('Opened DB')"

# ----------------------
# HEALTHCHECK
# ----------------------

healthcheck:
	@$(PYTHON) -c "import requests, json; \
print(json.dumps(requests.get('http://localhost:8000/health').json(), indent=2)) if True else None"

# ----------------------
# CLEAN
# ----------------------

clean:
	@echo Cleaning...
	@$(PYTHON) -c "import shutil, os; [shutil.rmtree(d, ignore_errors=True) for d in ['.pytest_cache','htmlcov']]; [os.remove(f) for f in ['.coverage'] if os.path.exists(f)]"
	@echo Cleaned

# ----------------------
# LINT / FORMAT
# ----------------------

lint:
	@$(PYTHON) -m pylint agents backend orchestrator || echo Install pylint

format:
	@$(PYTHON) -m black . || echo Install black

lint-fix:
	@$(PYTHON) -m black .
	@$(PYTHON) -m isort . || echo Install isort

# ----------------------
# UTILITIES
# ----------------------

shell:
	@$(PYTHON)

demo:
	@$(PYTHON) -c "from integrations.data_warehouse.sqlite_client import init_db; \
from backend.services.agent_registry import initialise_agents; \
from config.settings import Settings; \
from orchestrator.controller import OrchestratorController; \
init_db(); settings=Settings(); initialise_agents(settings); \
controller=OrchestratorController(settings); \
print(controller.handle(message='Find vendors under 100k', session_id='demo'))"