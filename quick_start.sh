#!/bin/bash
# Quick start script for PilotH
# Usage: bash ./quick_start.sh

set -e

echo "🚀 PilotH Quick Start Setup"
echo "============================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $python_version"

# Create virtual environment if needed
if [ ! -d ".venv" ]; then
    echo "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment exists"
fi

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "${YELLOW}Installing dependencies...${NC}"
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

# Copy .env if not exists
if [ ! -f ".env" ]; then
    echo "${YELLOW}Creating .env file...${NC}"
    cp config/.env.example .env
    echo "✓ .env created (using Ollama as default)"
else
    echo "✓ .env already exists"
fi

# Initialize database
echo "${YELLOW}Initializing database...${NC}"
python3 << 'EOF'
from integrations.data_warehouse.sqlite_client import init_db
init_db(seed=True)
print("✓ Database initialized and seeded")
EOF

# Run quick tests
echo ""
echo "${YELLOW}Running quick validation tests...${NC}"
python3 << 'EOF'
import sys
from integrations.data_warehouse.sqlite_client import init_db
from backend.services.agent_registry import initialise_agents
from config.settings import Settings

try:
    init_db()
    settings = Settings()
    print("  ✓ Settings loaded")
    
    # Check LLM availability
    from llm.model_factory import get_llm
    llm = get_llm()
    print("  ✓ LLM provider ready")
    
    # Check agents can be registered
    from agents.vendor_management.agent import VendorManagementAgent
    print("  ✓ Vendor Management Agent available")
    
    from agents.communication.agent import MeetingCommunicationAgent
    print("  ✓ Communication Agent available")
    
except Exception as e:
    print(f"  ✗ Validation failed: {e}")
    sys.exit(1)
EOF

echo ""
echo "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Start API server:"
echo "     uvicorn backend.api.main:app --reload --port 8000"
echo ""
echo "  2. In another terminal, check health:"
echo "     curl http://localhost:8000/health"
echo ""
echo "  3. Run tests:"
echo "     python3 tests/test_vendor_management.py"
echo ""
