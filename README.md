# PilotH — Enterprise Multi-Agent AI Orchestration Platform

> **Production-grade, modular multi-agent system built on LangGraph, LangChain, Pydantic v2, and FastAPI.**
> Every layer is decoupled, every file has one responsibility, and every external call is replaceable.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Folder Structure](#3-folder-structure)
4. [File-by-File Reference](#4-file-by-file-reference)
5. [Running the Project](#5-running-the-project)
6. [How to Add a New Agent — Step-by-Step](#6-how-to-add-a-new-agent--step-by-step)
7. [How to Add a New Tool to an Existing Agent](#7-how-to-add-a-new-tool-to-an-existing-agent)
8. [How to Add a New Tool to a Shared Tool Category](#8-how-to-add-a-new-tool-to-a-shared-tool-category)
9. [How to Add New Database Tables](#9-how-to-add-new-database-tables)
10. [How to Add a New API Route](#10-how-to-add-a-new-api-route)
11. [How to Add a New LLM Provider](#11-how-to-add-a-new-llm-provider)
12. [Environment Configuration](#12-environment-configuration)
13. [Testing](#13-testing)
14. [Design Principles](#14-design-principles)

---

## 1. System Overview

PilotH is a **multi-agent AI orchestration platform** designed for enterprise automation.
It routes natural language user requests to specialised AI agents. Each agent has:

- Its own **LangGraph** state machine (a directed workflow)
- A set of **single-responsibility tools** (database calls, LLM calls, external APIs)
- **Schema-validated** inputs and outputs (Pydantic v2)
- **Human-in-the-Loop (HITL)** integration for high-risk actions
- Access to **shared memory** (session + global context)

### Implemented Agents

| Agent | Module Key | Capabilities |
|---|---|---|
| Vendor Management | `vendor_management` | Best-fit ranking, SLA monitoring, contract parsing, scorecard, risk assessment, financial analysis, agreement expiry tracking, knowledge base search |
| Meetings & Communication | `meetings_communication` | Smart scheduling, summarization, briefings, sentiment, follow-ups |
| Knowledge Base | `knowledge_base` | Semantic search across vendor documents, agreements, communications, and policies |

### Key Features (v1.1)

- **Natural Language Input**: Accept plain text prompts instead of structured JSON
- **Intelligent Intent Parsing**: Advanced LLM-based intent detection with automatic tool routing
- **Comprehensive Logging**: Detailed logging for all agent and tool executions with PII masking
- **Advanced PII Protection**: Robust data sanitization for emails, phones, SSNs, credit cards, IPs, and more
- **Knowledge Base Integration**: Automatic semantic search across all document collections
- **Smart Output Formatting**: Clean, user-focused responses with unnecessary data filtered out
- **LLM Fallback Chain**: Automatic fallback from OpenAI → Groq → Ollama with connection validation
- **Agreement Expiry Notifications**: 7-day advance warnings for contract renewals
- **Risk Assessment Tools**: Financial, operational, compliance, and concentration risk analysis
- **Financial Analysis**: Spending optimization, budget tracking, and market comparisons
- **Interactive Simulations**: Contract negotiation, SLA violation response, and budget planning scenarios

---

## 2. Architecture

```
User Request (REST / WebSocket)
        │
        ▼
  FastAPI Backend  (backend/api/)
        │
        ▼
  Orchestrator  (orchestrator/)
   ├── IntentParser      — LLM or keyword routing
   ├── TaskDecomposer    — splits complex requests
   ├── AgentRouter       — dispatches to registered agent
   └── OrchestratorController — top-level coordinator
        │
        ▼
  Agent Registry  (backend/services/agent_registry.py)
   └── Registered Agents
        │
        ├── VendorManagementAgent       (agents/vendor_management/)
        │    ├── LangGraph StateGraph   (graph.py)
        │    ├── Nodes                  (nodes/*.py)
        │    └── Tools                  (tools/*.py)
        │
        └── MeetingCommunicationAgent   (agents/communication/)
             ├── LangGraph StateGraph   (graph.py)
             ├── Nodes                  (nodes/*.py)
             └── Tools                  (tools/*.py)
        │
        ▼
  Shared Infrastructure
   ├── LLM Layer         (llm/)           — OpenAI / Groq / Ollama fallback chain
   ├── Token Counter     (llm/token_counter.py)
   ├── Memory            (memory/)        — Session store + Global context (SQLite)
   ├── Data Access Layer (integrations/data_warehouse/)     — All SQL in one place
   ├── Tool Base Class   (tools/base_tool.py)
   ├── Schemas           (schemas/)       — Shared Pydantic models
   └── HITL Manager      (human_loop/manager.py)
```

### Key Design Rules

1. **No SQL outside DAL files** — all queries live in `integrations/data_warehouse/*.py`
2. **No hardcoded data** — everything is seeded via `init_db()`, replaceable with real APIs
3. **One responsibility per tool** — each tool does exactly one thing
4. **LLM calls always have fallbacks** — rule-based or mock if LLM is unavailable
5. **Pydantic v2 everywhere** — all inputs/outputs are typed and validated

---

## 2.5 API Usage Examples

### Natural Language Input (Recommended)

```bash
# Vendor Management
curl -X POST http://localhost:8000/agents/vendor_management/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Find the best cloud vendor within $50,000 budget"}'

# Knowledge Base Search
curl -X POST http://localhost:8000/agents/knowledge_base/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What do we know about vendor compliance requirements?"}'

# Meeting Scheduling
curl -X POST http://localhost:8000/agents/meetings_communication/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Schedule a meeting with the vendor team next Tuesday at 2pm"}'
```

### Legacy JSON Input (Still Supported)

```bash
curl -X POST http://localhost:8000/agents/vendor_management/run \
  -H "Content-Type: application/json" \
  -d '{"input": {"action": "find_best", "service_tags": ["cloud"], "budget_usd": 50000}}'
```

### Response Format

```json
{
  "session_id": "abc-123-def",
  "response": "I found 3 vendors matching your criteria. The top recommendation is CloudServe Inc. with a score of 8.5/10.",
  "data": {
    "vendors": [
      {
        "name": "CloudServe Inc.",
        "overall_score": 8.5,
        "monthly_cost": 45000
      }
    ]
  },
  "metadata": {
    "agent": "vendor_management",
    "action": "find_best",
    "confidence": 0.92,
    "token_usage": {"total": 1250, "prompt": 800, "completion": 450}
  }
}
```

---

## 2.6 Recent Improvements (v1.1)

### Natural Language Processing
- **Intent Parser**: Advanced LLM-based intent detection with confidence scoring
- **Tool Registry**: Comprehensive tool descriptions for accurate routing
- **Multi-turn Context**: Conversation history awareness for better understanding

### Enhanced Security & Privacy
- **Advanced PII Sanitization**: Masks emails, phones, SSNs, credit cards, IPs, names, addresses
- **Input Sanitization**: All user inputs sanitized before LLM processing
- **Output Filtering**: Sensitive data removed from responses
- **Field-level Protection**: Automatic detection of sensitive field names

### Comprehensive Logging
- **Agent Execution Logs**: Detailed timing and success/failure tracking
- **Tool Execution Logs**: Per-tool performance metrics and retry information
- **PII-safe Logging**: All logs sanitized before storage
- **Structured JSON Logs**: Easy aggregation and monitoring

### Knowledge Base Integration
- **Semantic Search**: Vector-based search across all document collections
- **Multi-collection Support**: Agreements, communications, vendor data, financial reports
- **Automatic Routing**: KB queries detected and routed automatically
- **Relevance Scoring**: Results ranked by semantic similarity

### Robust Fallbacks
- **LLM Chain**: OpenAI → Groq → Ollama with automatic failover
- **Connection Validation**: Pre-flight checks before LLM usage
- **Retry Logic**: Configurable retries with exponential backoff
- **Graceful Degradation**: Keyword-based fallbacks when LLMs fail

### Smart Output Formatting
- **User-focused Responses**: Clean, readable summaries
- **Data Filtering**: Unnecessary internal fields removed
- **Contextual Summaries**: Agent-specific response formatting
- **PII-free Outputs**: All responses sanitized for safety

---

## 3. Folder Structure

```
PilotH/
├── agents/                          # All agents live here
│   ├── base_agent.py                # BaseAgent abstract class (inherit this)
│   ├── registry.py                  # ToolRegistry — central tool inventory
│   ├── vendor_management/           # Vendor Management Agent
│   │   ├── __init__.py
│   │   ├── agent.py                 # VendorManagementAgent class
│   │   ├── graph.py                 # LangGraph StateGraph definition
│   │   ├── schemas.py               # Pydantic input/output + TypedDict state
│   │   ├── nodes/                   # One .py per workflow phase
│   │   │   ├── fetch_vendor.py
│   │   │   ├── evaluate.py
│   │   │   ├── risk_detect.py
│   │   │   └── summarize.py
│   │   └── tools/                   # One .py per tool
│   │       ├── vendor_search.py
│   │       ├── vendor_matcher.py
│   │       ├── contract_parser.py
│   │       ├── sla_monitor.py
│   │       ├── milestone_tracker.py
│   │       └── vendor_scorecard.py
│   └── communication/               # Meetings & Communication Agent
│       ├── __init__.py
│       ├── agent.py                 # MeetingCommunicationAgent class
│       ├── graph.py                 # 3-branch LangGraph StateGraph
│       ├── schemas.py               # MeetingRequestInput, MeetingAgentOutput, MeetingState
│       ├── nodes/
│       │   ├── scheduling.py        # resolve_participants → availability → slots → create_event
│       │   ├── summarization.py     # transcript → key_points → summary → followup
│       │   ├── briefing.py          # context → sentiment → agenda → briefing
│       │   └── common.py            # finalize_node, hitl_check_node
│       └── tools/
│           ├── calendar_tools.py    # GoogleCalendarCreate + Availability
│           ├── timezone_tool.py
│           ├── email_draft_tool.py
│           ├── briefing_tool.py     # ParticipantBriefingTool — reads persons table
│           ├── sentiment_tool.py
│           ├── summarizer_tool.py
│           ├── agenda_tool.py
│           ├── slack_tool.py
│           ├── action_tracker_tool.py
│           └── conflict_resolver_tool.py
│
├── backend/                         # FastAPI application
│   ├── api/
│   │   ├── main.py                  # App entry point, lifespan, CORS, routers
│   │   ├── dependencies.py          # FastAPI DI helpers (get_settings, get_vendor_agent)
│   │   ├── middleware.py
│   │   └── routes/
│   │       ├── health.py            # GET /health
│   │       ├── vendor_routes.py     # Vendor Management endpoints
│   │       ├── agent_routes.py      # Generic /agents/{name}/run endpoint
│   │       └── human_loop_routes.py # HITL approve/reject
│   ├── services/
│   │   └── agent_registry.py        # Instantiates + registers all agents at startup
│   └── websocket/
│       └── manager.py
│
├── config/
│   ├── settings.py                  # Pydantic-settings: all config from env / .env
│   └── .env.example                 # Template for environment variables
│
├── integrations/                    # External service clients + Data Access Layer
│   ├── data_warehouse/
│   │   ├── sqlite_client.py         # Connection manager + init_db() + vendor schema
│   │   ├── vendor_db.py             # ALL vendor SQL (search, SLA, milestones…)
│   │   └── meeting_db.py            # ALL meetings/persons SQL (disambiguation, calendar…)
│   ├── google_calendar/             # Real Google Calendar API client (stub)
│   ├── crm/                         # HubSpot / Salesforce stubs
│   └── finance/                     # ERP connector stub
│
├── llm/
│   ├── model_factory.py             # get_llm() — OpenAI → Groq → Ollama fallback chain
│   ├── token_counter.py             # Thread-safe token + cost tracking
│   ├── base.py
│   ├── openai_client.py
│   ├── groq_client.py
│   └── ollama_client.py
│
├── memory/
│   ├── session_store.py             # In-process short-term session memory (TTL)
│   ├── global_context.py            # SQLite-backed persistent cross-agent memory
│   ├── vector_store.py              # ChromaDB/FAISS vector store stub
│   └── embeddings.py
│
├── orchestrator/
│   ├── controller.py                # OrchestratorController — main entry point
│   ├── intent_parser.py             # LLM + keyword routing
│   ├── agent_router.py              # Dispatches to registered agents
│   ├── task_decomposer.py
│   ├── memory_manager.py
│   ├── fallback_handler.py
│   └── workflow_engine.py
│
├── schemas/                         # Global shared Pydantic schemas
│   ├── common.py                    # BaseResponse, ErrorResponse, PaginatedResponse
│   ├── user_request.py              # UserRequest, AgentTaskRequest
│   ├── agent_io.py                  # AgentInput, AgentOutput
│   ├── tool_io.py                   # ToolInput, ToolOutput
│   ├── human_loop.py                # HITLRequest, HITLDecision
│   └── memory.py                    # MemoryEntry, ContextUpdate
│
├── tools/                           # Shared utility tools (not agent-specific)
│   ├── base_tool.py                 # StructuredTool abstract base class ← inherit this
│   ├── analytics_tools/
│   ├── api_tools/
│   ├── calendar_tools/
│   ├── communication_tools/
│   ├── data_tools/
│   └── file_tools/
│
├── human_loop/
│   └── manager.py                   # HITLManager — approval queue + NodeInterrupt
│
├── graphs/
│   ├── orchestration_graph.py       # Top-level multi-agent graph
│   └── subgraph_loader.py
│
├── observability/
│   ├── logger.py
│   ├── langsmith_config.py
│   └── metrics.py
│
└── tests/
    ├── test_vendor_management.py    # 35-test vendor agent suite
    └── test_meetings_agent.py       # 41-test meetings agent suite
```

---

## 4. File-by-File Reference

### Core Build Blocks

| File | What it Does | When You Touch It |
|---|---|---|
| `tools/base_tool.py` | Abstract `StructuredTool` class. All tools inherit this. | Never (read only to understand the interface) |
| `agents/base_agent.py` | Abstract `BaseAgent` class. All agents inherit this. | Never (read only) |
| `agents/registry.py` | `ToolRegistry` — register/lookup tools by name and agent | Automatically used; never touch directly |
| `backend/services/agent_registry.py` | **Instantiates every agent at startup** and puts them in `_agents` dict | Add 3 lines when adding a new agent |
| `integrations/data_warehouse/sqlite_client.py` | Connection manager + `init_db()` entry point | Call `create_*_tables()` from here when adding new DB modules |
| `llm/model_factory.py` | `get_llm()` — returns best available LLM | Add a new provider here |
| `llm/token_counter.py` | Token + cost tracking | Import `get_token_counter()` anywhere |
| `memory/session_store.py` | Short-term session memory (in-process) | Import `get_session_store()` from any agent |
| `memory/global_context.py` | SQLite persistent cross-agent memory | Import `get_global_context()` to read/write shared facts |
| `config/settings.py` | All environment config via Pydantic-settings | Add new config keys here |
| `orchestrator/intent_parser.py` | Routes `"schedule a meeting"` → `meetings_communication` agent | Add keyword mappings when adding agents |
| `backend/api/main.py` | FastAPI app bootstrap. Includes all routers. | Import and include your new router here |

### Data Access Layer (DAL)

| File | Tables Managed | Key Functions |
|---|---|---|
| `integrations/data_warehouse/sqlite_client.py` | Vendor schema (11 tables) | `init_db()`, `get_db_connection()` |
| `integrations/data_warehouse/vendor_db.py` | vendors, contracts, SLAs, milestones, projects | `search_vendors()`, `find_best_vendors_for_service()`, `get_sla_compliance()` |
| `integrations/data_warehouse/meeting_db.py` | persons, calendar_events, meetings, attendees, agendas, action_items | `find_persons()`, `get_person_by_email()`, `create_meeting()`, `get_meeting_full()` |

---

## 5. Running the Project

### Prerequisites

```bash
# Python 3.11+ (project uses .venv with Python 3.13)
# Ollama running locally (for LLM): https://ollama.ai
ollama pull qwen2.5:3b
```

### Setup

```bash
git clone <repo>
cd PilotH

# Create venv (if not already present)
uv venv
# or: python3 -m venv .venv

# Install dependencies (uv is pre-installed in .venv)
uv pip install -r requirements.txt

# Copy and configure environment
cp config/.env.example .env
# Edit .env — set OPENAI_API_KEY, GROQ_API_KEY, or leave blank for Ollama
```

### Run Tests

```bash
# Vendor Management Agent (35 tests)
.venv/bin/python3 tests/test_vendor_management.py

# Meetings & Communication Agent (41 tests)
.venv/bin/python3 tests/test_meetings_agent.py
```

### Start API Server

```bash
.venv/bin/python3 -m uvicorn backend.api.main:app --reload --port 8000
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | DB connectivity check |
| POST | `/agents/{name}/run` | Run any registered agent |
| GET | `/vendors/search` | Search vendors by service tag |
| POST | `/vendors/find-best` | Best-fit vendor for a project |
| GET | `/vendors/{id}/scorecard` | Full vendor scorecard |
| GET | `/vendors/{id}/sla` | SLA compliance data |
| POST | `/human-loop/approve` | Approve a HITL decision |
| POST | `/human-loop/reject` | Reject a HITL decision |

---

## 6. How to Add a New Agent — Step-by-Step

This is the complete guide to add a fully-integrated agent (e.g., a **Finance Agent**).

### Step 1 — Create the agent folder

```
agents/finance/
├── __init__.py
├── agent.py
├── graph.py
├── schemas.py
├── nodes/
│   ├── __init__.py
│   └── analysis.py
└── tools/
    ├── __init__.py
    └── budget_tool.py
```

### Step 2 — Define schemas (`agents/finance/schemas.py`)

```python
from __future__ import annotations
from typing import Any, Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field

class FinanceInput(BaseModel):
    action: str = Field("analyze_budget")           # The action this agent should take
    department: Optional[str] = None
    fiscal_year: Optional[int] = None
    context: Optional[str] = None

class FinanceOutput(BaseModel):
    status: str = "success"
    action: str
    result: Dict[str, Any] = {}
    summary: Optional[str] = None
    error: Optional[str] = None

class FinanceState(TypedDict, total=False):
    action: str
    department: Optional[str]
    fiscal_year: Optional[int]
    context: Optional[str]
    budget_data: Dict[str, Any]
    analysis: Optional[str]
    error: Optional[str]
    messages: List[Any]
```

> **Rule:** `State` is a `TypedDict` (for LangGraph). Input/Output are `BaseModel` (for API + validation).

### Step 3 — Write tools (`agents/finance/tools/budget_tool.py`)

```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool   # ← always inherit this


class BudgetQueryInput(BaseModel):
    department: str
    fiscal_year: int


class BudgetQueryOutput(BaseModel):
    department: str
    fiscal_year: int
    allocated: float
    spent: float
    variance: float
    found: bool


class BudgetQueryTool(StructuredTool):
    """Fetch budget allocation vs spending for a department."""
    name: str = "budget_query"
    description: str = "Fetch budget allocation and spending data for a department."
    args_schema: type[BaseModel] = BudgetQueryInput

    def execute(self, inp: BudgetQueryInput) -> BudgetQueryOutput:
        # PRODUCTION: Call your ERP / Finance API here
        # For now: query the database via your DAL
        # from integrations.data_warehouse.finance_db import get_budget
        # data = get_budget(inp.department, inp.fiscal_year)
        return BudgetQueryOutput(
            department=inp.department,
            fiscal_year=inp.fiscal_year,
            allocated=500000.0,
            spent=312000.0,
            variance=188000.0,
            found=True,
        )
```

> **Rules for tools:**
> - Always inherit `StructuredTool` from `tools/base_tool.py`
> - Always define `args_schema` (Pydantic input model)
> - `execute()` receives a **validated** input object — never raw dicts
> - **No SQL in tools** — call DAL functions instead
> - Return a Pydantic model or a dict

### Step 4 — Export tools (`agents/finance/tools/__init__.py`)

```python
from .budget_tool import BudgetQueryTool
__all__ = ["BudgetQueryTool"]
```

### Step 5 — Write graph nodes (`agents/finance/nodes/analysis.py`)

```python
from __future__ import annotations
from typing import Any, Dict
from langchain_core.messages import AIMessage
from agents.finance.schemas import FinanceState


def fetch_budget_node(state: FinanceState) -> Dict[str, Any]:
    """Fetch budget data for the requested department."""
    from agents.finance.tools.budget_tool import BudgetQueryTool, BudgetQueryInput

    tool = BudgetQueryTool()
    result = tool.execute(BudgetQueryInput(
        department=state.get("department", "Engineering"),
        fiscal_year=state.get("fiscal_year", 2025),
    ))
    return {
        "budget_data": result.model_dump(),
        "messages": [AIMessage(content=f"Budget fetched for {result.department}.")],
    }


def analyze_budget_node(state: FinanceState) -> Dict[str, Any]:
    """Generate analysis narrative using LLM or rule-based fallback."""
    budget = state.get("budget_data", {})
    variance = budget.get("variance", 0)
    status = "under budget" if variance > 0 else "over budget"
    analysis = (
        f"Department {budget.get('department')} is {status} by "
        f"${abs(variance):,.0f} for FY{budget.get('fiscal_year')}."
    )
    return {
        "analysis": analysis,
        "messages": [AIMessage(content=analysis)],
    }
```

> **Rules for nodes:**
> - Accept `state: YourState` and return `Dict[str, Any]` with only the **keys that changed**
> - Import tools **inside the function** (avoids circular imports)
> - All external I/O (DB, API, LLM) happens in tools — nodes just orchestrate

### Step 6 — Export nodes (`agents/finance/nodes/__init__.py`)

```python
from .analysis import fetch_budget_node, analyze_budget_node
__all__ = ["fetch_budget_node", "analyze_budget_node"]
```

### Step 7 — Build the graph (`agents/finance/graph.py`)

```python
from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from .schemas import FinanceState
from .nodes import fetch_budget_node, analyze_budget_node


def build_finance_graph():
    builder = StateGraph(FinanceState)

    builder.add_node("fetch_budget",    fetch_budget_node)
    builder.add_node("analyze_budget",  analyze_budget_node)

    builder.add_edge(START,            "fetch_budget")
    builder.add_edge("fetch_budget",   "analyze_budget")
    builder.add_edge("analyze_budget", END)

    return builder.compile()
```

> **HITL:** Add `interrupt_after=["node_name"]` to `builder.compile(checkpointer=...)` for approval gates.

### Step 8 — Write the agent class (`agents/finance/agent.py`)

```python
from __future__ import annotations
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel
from agents.base_agent import BaseAgent
from config.settings import Settings
from human_loop.manager import HITLManager

from .schemas import FinanceInput, FinanceOutput, FinanceState
from .graph import build_finance_graph
from .tools import BudgetQueryTool


class FinanceAgent(BaseAgent):
    """Finance & Budget Analysis Agent."""
    name: str = "finance"

    def __init__(self, config: Settings, tool_registry=None, hitl_manager: Optional[HITLManager] = None):
        super().__init__(config, tool_registry, hitl_manager)
        self._register_tools()

    def _register_tools(self) -> None:
        if not self.tool_registry:
            return
        for tool in [BudgetQueryTool()]:
            self.tool_registry.register_tool(tool, self.name)

    @property
    def input_schema(self) -> Type[BaseModel]:
        return FinanceInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return FinanceOutput

    def get_subgraph(self):
        return build_finance_graph()

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        validated = FinanceInput(**input_data)
        state_input: Dict[str, Any] = {
            "action":      validated.action,
            "department":  validated.department,
            "fiscal_year": validated.fiscal_year,
            "context":     validated.context,
            "messages":    [],
        }
        graph  = self.get_subgraph()
        result: FinanceState = graph.invoke(state_input)
        return self.validate_output({
            "status":  "success" if not result.get("error") else "error",
            "action":  validated.action,
            "result":  result.get("budget_data", {}),
            "summary": result.get("analysis"),
            "error":   result.get("error"),
        })
```

### Step 9 — Export the agent (`agents/finance/__init__.py`)

```python
from .agent import FinanceAgent
from .schemas import FinanceInput, FinanceOutput
__all__ = ["FinanceAgent", "FinanceInput", "FinanceOutput"]
```

### Step 10 — Register the agent at startup

Open `backend/services/agent_registry.py` and add **3 lines** inside `initialise_agents()`:

```python
# ── Finance Agent ────────────────────────────────────────
from agents.finance.agent import FinanceAgent
finance_agent = FinanceAgent(config=config, tool_registry=registry, hitl_manager=hitl)
_agents["finance"] = finance_agent
```

### Step 11 — Add intent routing

Open `orchestrator/intent_parser.py` and add keywords to `_ROUTING_TABLE`:

```python
_ROUTING_TABLE = {
    # ... existing entries ...
    "budget":       ("finance", "analyze_budget"),
    "finance":      ("finance", "analyze_budget"),
    "fiscal":       ("finance", "analyze_budget"),
    "spend":        ("finance", "analyze_budget"),
}
```

### Step 12 — Add an API route (optional)

Create `backend/api/routes/finance_routes.py`:

```python
from fastapi import APIRouter, Depends
from backend.api.dependencies import get_settings
from backend.services.agent_registry import get_agent

router = APIRouter(prefix="/finance", tags=["Finance"])

@router.post("/analyze")
async def analyze_budget(department: str, fiscal_year: int = 2025):
    agent = get_agent("finance")
    return agent.execute({"action": "analyze_budget", "department": department, "fiscal_year": fiscal_year})
```

Then register it in `backend/api/main.py`:

```python
from backend.api.routes.finance_routes import router as finance_router
app.include_router(finance_router)
```

### Step 13 — Write tests (`tests/test_finance_agent.py`)

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.data_warehouse.sqlite_client import init_db
init_db()

from agents.finance.tools.budget_tool import BudgetQueryTool, BudgetQueryInput
out = BudgetQueryTool().execute(BudgetQueryInput(department="Engineering", fiscal_year=2025))
assert out.found, "Budget tool should return data"
print("✓ BudgetQueryTool")

from agents.finance.nodes.analysis import fetch_budget_node, analyze_budget_node
s = fetch_budget_node({"action": "analyze_budget", "department": "Engineering", "fiscal_year": 2025})
assert "budget_data" in s
s2 = analyze_budget_node({**s})
assert s2.get("analysis")
print("✓ Graph nodes")

print("\nAll finance agent tests passed!")
```

```bash
.venv/bin/python3 tests/test_finance_agent.py
```

---

## 7. How to Add a New Tool to an Existing Agent

Example: adding a `CurrencyConverterTool` to the **Finance Agent**.

### Step 1 — Create the tool file

`agents/finance/tools/currency_tool.py`:

```python
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool

class CurrencyInput(BaseModel):
    amount: float
    from_currency: str
    to_currency: str

class CurrencyOutput(BaseModel):
    converted_amount: float
    rate: float
    from_currency: str
    to_currency: str

class CurrencyConverterTool(StructuredTool):
    name: str = "currency_converter"
    description: str = "Convert a monetary amount between currencies."
    args_schema: type[BaseModel] = CurrencyInput

    def execute(self, inp: CurrencyInput) -> CurrencyOutput:
        # PRODUCTION: Call FX API (e.g., Open Exchange Rates)
        # Mock rate:
        rates = {"USD_INR": 83.5, "USD_EUR": 0.92, "INR_USD": 0.012}
        key = f"{inp.from_currency}_{inp.to_currency}"
        rate = rates.get(key, 1.0)
        return CurrencyOutput(
            converted_amount=inp.amount * rate,
            rate=rate,
            from_currency=inp.from_currency,
            to_currency=inp.to_currency,
        )
```

### Step 2 — Export it

In `agents/finance/tools/__init__.py`, add:

```python
from .currency_tool import CurrencyConverterTool
__all__ = ["BudgetQueryTool", "CurrencyConverterTool"]
```

### Step 3 — Register in the agent

In `agents/finance/agent.py`, add to `_register_tools()`:

```python
from .tools import BudgetQueryTool, CurrencyConverterTool

for tool in [BudgetQueryTool(), CurrencyConverterTool()]:
    self.tool_registry.register_tool(tool, self.name)
```

### Step 4 — Use it in a node

In any node file, import and call it:

```python
from agents.finance.tools.currency_tool import CurrencyConverterTool, CurrencyInput
result = CurrencyConverterTool().execute(CurrencyInput(amount=1000, from_currency="USD", to_currency="INR"))
```

> **That's it.** No other files need to change.

---

## 8. How to Add a New Tool to a Shared Tool Category

Shared tools in `tools/` are available to **all agents**.

Example: adding a `PDFSummarizerTool` to `tools/file_tools/`.

### Step 1 — Create the tool

`tools/file_tools/pdf_summarizer.py`:

```python
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool

class PDFInput(BaseModel):
    file_path: str = Field(..., description="Absolute path to the PDF file")
    max_pages: int = Field(10, description="Maximum pages to process")

class PDFOutput(BaseModel):
    text: str
    page_count: int
    summary: str

class PDFSummarizerTool(StructuredTool):
    name: str = "pdf_summarizer"
    description: str = "Extract and summarise text from a PDF document."
    args_schema: type[BaseModel] = PDFInput

    def execute(self, inp: PDFInput) -> PDFOutput:
        # PRODUCTION: Use PyMuPDF or pdfplumber
        # import fitz
        # doc = fitz.open(inp.file_path)
        # text = "\n".join(page.get_text() for page in doc[:inp.max_pages])
        text = f"[Mock] Extracted text from {inp.file_path} ({inp.max_pages} pages max)"
        return PDFOutput(text=text, page_count=1, summary=text[:200])
```

### Step 2 — Export it

In `tools/file_tools/__init__.py`:

```python
from .pdf_summarizer import PDFSummarizerTool
```

### Step 3 — Use it in any agent's tool or node

```python
from tools.file_tools.pdf_summarizer import PDFSummarizerTool, PDFInput
result = PDFSummarizerTool().execute(PDFInput(file_path="/docs/contract.pdf"))
```

---

## 9. How to Add New Database Tables

All SQL lives exclusively in `integrations/data_warehouse/`. Never write SQL in tools or nodes.

### Step 1 — Create a new DAL module

`integrations/data_warehouse/finance_db.py`:

```python
"""Finance DAL — ALL SQL for finance tables."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .sqlite_client import get_db_connection

_FINANCE_DDL = [
    """CREATE TABLE IF NOT EXISTS budgets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        department  TEXT    NOT NULL,
        fiscal_year INTEGER NOT NULL,
        allocated   REAL    NOT NULL,
        spent       REAL    DEFAULT 0.0,
        UNIQUE(department, fiscal_year)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_budgets_dept ON budgets(department)",
]

def create_finance_tables() -> None:
    with get_db_connection() as conn:
        for stmt in _FINANCE_DDL:
            conn.execute(stmt)
        conn.commit()

def seed_finance_data() -> None:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM budgets")
        if cur.fetchone()[0] > 0:
            return
        budgets = [
            ("Engineering", 2025, 500000.0, 312000.0),
            ("Marketing",   2025, 200000.0, 189000.0),
            ("Finance",     2025, 150000.0,  90000.0),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO budgets(department, fiscal_year, allocated, spent) VALUES(?,?,?,?)",
            budgets
        )
        conn.commit()

def get_budget(department: str, fiscal_year: int) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM budgets WHERE department=? AND fiscal_year=?",
            (department, fiscal_year)
        )
        row = cur.fetchone()
        return dict(row) if row else None
```

### Step 2 — Hook into `init_db()`

Open `integrations/data_warehouse/sqlite_client.py` and add inside `init_db()`:

```python
def init_db(seed: bool = True) -> None:
    # ... existing vendor tables ...

    # Finance tables
    from integrations.data_warehouse.finance_db import create_finance_tables, seed_finance_data
    create_finance_tables()
    if seed:
        seed_finance_data()
```

### Step 3 — Use DAL functions from tools (never raw SQL)

```python
# In agents/finance/tools/budget_tool.py
def execute(self, inp: BudgetQueryInput) -> BudgetQueryOutput:
    from integrations.data_warehouse.finance_db import get_budget
    data = get_budget(inp.department, inp.fiscal_year)
    if not data:
        return BudgetQueryOutput(..., found=False)
    return BudgetQueryOutput(
        department=data["department"],
        allocated=data["allocated"],
        spent=data["spent"],
        variance=data["allocated"] - data["spent"],
        found=True,
    )
```

---

## 10. How to Add a New API Route

### Step 1 — Create the route file

`backend/api/routes/finance_routes.py`:

```python
from fastapi import APIRouter, HTTPException
from backend.services.agent_registry import get_agent

router = APIRouter(prefix="/finance", tags=["Finance Agent"])

@router.get("/budget/{department}")
async def get_budget_summary(department: str, fiscal_year: int = 2025):
    agent = get_agent("finance")
    if not agent:
        raise HTTPException(503, "Finance agent not available")
    return agent.execute({
        "action":      "analyze_budget",
        "department":  department,
        "fiscal_year": fiscal_year,
    })
```

### Step 2 — Register in `backend/api/main.py`

```python
from backend.api.routes.finance_routes import router as finance_router

# Inside create_app() or at module level, after other routers:
app.include_router(finance_router)
```

---

## 11. How to Add a New LLM Provider

### Step 1 — Add credentials to `config/settings.py`

```python
# e.g., for Anthropic Claude
anthropic_api_key: str = Field("", description="Anthropic API key")
anthropic_model:   str = Field("claude-3-5-sonnet-20241022")
```

### Step 2 — Create the client

`llm/anthropic_client.py`:

```python
def get_anthropic_llm(model: str, **kwargs):
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=model, **kwargs)
```

### Step 3 — Add to the fallback chain in `llm/model_factory.py`

```python
def get_llm(temperature: float = 0.1, **kwargs):
    settings = Settings()

    # Try Anthropic
    if settings.anthropic_api_key:
        try:
            from llm.anthropic_client import get_anthropic_llm
            return get_anthropic_llm(model=settings.anthropic_model, temperature=temperature, **kwargs)
        except Exception:
            pass

    # ... existing OpenAI → Groq → Ollama chain ...
```

### Step 4 — Add to `config/.env.example`

```ini
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

---

## 12. Environment Configuration

Copy `config/.env.example` to `.env` at the project root and fill in your values:

```ini
# Primary LLM (openai | groq | ollama)
LLM_PRIMARY=ollama

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Groq (fast LLaMA)
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant

# Ollama (local, always available as fallback)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b

# Database
SQLITE_DB_PATH=pilot_db.sqlite

# Human-in-the-Loop
HITL_THRESHOLD=0.7

# LangSmith (optional tracing)
LANGSMITH_API_KEY=
LANGSMITH_TRACING_V2=false

# API Server
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

**Security:** Never commit `.env`. Add it to `.gitignore`.

---

## 13. Testing

### Run all tests

```bash
# Reset DB and run both suites
rm -f pilot_db.sqlite
.venv/bin/python3 tests/test_vendor_management.py
.venv/bin/python3 tests/test_meetings_agent.py
```

### Current test results

```
Vendor Management: 35 / 35  ✓
Meetings & Communication: 41 / 41  ✓
```

### Writing tests for your new agent

Follow this pattern in `tests/test_finance_agent.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.data_warehouse.sqlite_client import init_db
init_db()  # always call this first

# 1. Test DAL
from integrations.data_warehouse.finance_db import get_budget
row = get_budget("Engineering", 2025)
assert row is not None, "Budget data should exist after seeding"
print("✓ DAL: get_budget")

# 2. Test tools individually (no graph, no LLM)
from agents.finance.tools.budget_tool import BudgetQueryTool, BudgetQueryInput
out = BudgetQueryTool().execute(BudgetQueryInput(department="Engineering", fiscal_year=2025))
assert out.found
print("✓ Tool: BudgetQueryTool")

# 3. Test graph nodes in isolation
from agents.finance.nodes.analysis import fetch_budget_node, analyze_budget_node
state = {"action": "analyze_budget", "department": "Engineering", "fiscal_year": 2025}
s1 = fetch_budget_node(state)
assert "budget_data" in s1
s2 = analyze_budget_node({**state, **s1})
assert s2.get("analysis")
print("✓ Nodes: fetch_budget → analyze_budget")

print("\nAll tests passed!")
```

---

## 13.5 Real-Time WebSocket Updates & Broadcast Architecture

PilotH uses WebSockets to push real-time updates to connected clients instead of polling.

### System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  FastAPI Server (main.py)               │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────┐        ┌─────────────────────┐ │
│  │ TaskQueueManager    │        │ WebSocketManager    │ │
│  │  (backend/services) │───────▶│  (backend/websocket)│ │
│  └─────────────────────┘        └─────────────────────┘ │
│        │                              │                 │
│        │ .broadcast_task_progress()   │ .get_stats()    │
│        │ .broadcast_task_completed()  │                 │
│        ▼                              ▼                 │
│    [Task Queue DB]         [ConnectionManager]         │
│    (task_queue table)       (active WebSockets)        │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Agent    │  │ HITL     │  │ Escalation           │  │
│  │ Execution│  │ Manager  │  │ Engine               │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│       │              │                 │                │
│       └──────────────┼─────────────────┘                │
│                      │                                   │
│                Calls broadcast_*()                      │
└──────────────────────┼───────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    [Browser]    [Mobile App]  [Admin Dashboard]
      Client        Client         Client
      (JS)          (Native)      (Real-time)
```

### Broadcasting via WebSocket

**From within a node (agent execution):**

```python
async def approve_contract_node(state):
    """Example: request approval during contract signing."""
    from backend.websocket.manager import get_websocket_manager
    
    ws = get_websocket_manager()
    
    # Broadcast approval request to specific session
    await ws.broadcast_approval_request(
        task_id=state.get("task_id"),
        session_id=state.get("session_id"),
        agent_name="vendor_management",
        action="sign_contract",
        context=f"Sign contract with {state['vendor_name']} for ${state['project_value']:,.0f}",
        risk_score=0.85,
        risk_items=[
            "External vendor requires executive approval",
            "Contract includes automatic renewal clause"
        ],
        expires_at=time.time() + 7200  # 2 hours
    )
    
    # Graph pauses here until human decides
    # (LangGraph checkpoint handles resumption)
    
    return {"approval_pending": True}
```

**From task queue (progress updates):**

```python
# In TaskQueueManager._execute_task():
await self._connection_manager.broadcast_to_session(
    session_id=task.session_id,
    message={
        "component_type": "agent_progress",
        "task_id": task.task_id,
        "agent_name": task.agent_name,
        "step": "Evaluating vendor contracts...",
        "progress_pct": 75,
        "status": "running"
    }
)
```

**From escalation engine (alerts):**

```python
# In EscalationEngine.escalate():
await get_websocket_manager().broadcast_escalation(
    task_id=task_id,
    level="critical",  # low | medium | high | critical
    agent_name=agent_name,
    message="Vendor risk score exceeded critical threshold. Auto-rejected contract signature.",
    session_id=session_id
)
```

### Frontend Integration (JavaScript)

```javascript
class PilotHClient {
  constructor(sessionId) {
    this.sessionId = sessionId;
    this.ws = new WebSocket(`ws://localhost:8000/ws?session_id=${sessionId}`);
    this.ws.onmessage = (event) => this.handleMessage(JSON.parse(event.data));
  }

  handleMessage(msg) {
    switch (msg.component_type) {
      case "agent_progress":
        this.updateProgressBar(msg.progress_pct, msg.step);
        break;
      case "approval_card":
        this.showApprovalModal(msg);
        break;
      case "task_complete":
        this.showResult(msg.summary, msg.result);
        break;
      case "alert":
        this.showAlert(msg.level, msg.message);
        break;
      case "error_card":
        this.showError(msg.error, msg.recoverable);
        break;
    }
  }

  submitApproval(taskId, approved, feedback = "") {
    fetch("http://localhost:8000/hitl/decision", {
      method: "POST",
      // Note: this will trigger auto-broadcast of decision via WebSocket
      body: JSON.stringify({ task_id: taskId, approved, feedback })
    });
  }
}
```

---

## 13.6 Task Queue & Async Execution

The Task Queue decouples request ingestion from agent execution:

```
Request → API → Enqueue Task → Immediately return task_id
                     │
                     ▼
              Background Worker [async]
              • Retry on failure
              • Sanitize PII
              • Generate LLM summary
              • Broadcast progress
              • Persist result
```

### Key Features

| Feature | How It Works | Benefit |
|---|---|---|
| **Async Processing** | Tasks execute in background pool (5 workers default) | API never blocks; frontends feel responsive |
| **Persistence** | All tasks saved to `task_queue` table | Survives server restart; can resume paused tasks |
| **Retry Logic** | Exponential backoff (2s, 4s, 8s, ...) | Handles transient API failures automatically |
| **PII Sanitization** | Payloads masked before storage | Legal compliance; sensitive data protected |
| **LLM Summaries** | Auto-generate human-friendly results | Users get explanations, not raw data |
| **Progress Tracking** | Real-time updates via WebSocket | Frontends show live progress bars |

### Configuration

```python
# In config/settings.py:
task_queue_max_workers: int = Field(5, description="Max concurrent task workers")
task_queue_enable_llm_summaries: bool = Field(True)
task_queue_enable_pii_sanitization: bool = Field(True)

# In backend/api/main.py lifespan:
from backend.services.task_queue import get_task_queue
queue = get_task_queue()
# Queue must be added to async startup:
# asyncio.create_task(queue.process_queue())
```

---

## 13.7 Real LLM Integration Best Practices

### Pattern 1: Rule-Based Fallback

Always provide a non-LLM alternative. **Never let a missing LLM crash the agent.**

```python
def classify_severity(alert_text: str) -> str:
    """Classify alert with LLM fallback to rule-based."""
    
    # Try LLM first (fast, accurate)
    try:
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage
        
        llm = get_llm(temperature=0.0)  # Deterministic
        prompt = f"""Classify as 'critical', 'high', 'medium', or 'low':
        {alert_text}
        Reply with ONLY the classification word."""
        
        response = llm.invoke([HumanMessage(content=prompt)])
        classification = response.content.strip().lower()
        
        if classification in ["critical", "high", "medium", "low"]:
            return classification
    except Exception as e:
        logger.warning("[Tool] LLM classification failed: %s", e)
    
    # Fallback: Rule-based classification
    keywords_critical = ["outage", "breach", "crash"]
    keywords_high = ["error", "warning", "timeout"]
    
    text_lower = alert_text.lower()
    if any(kw in text_lower for kw in keywords_critical):
        return "critical"
    if any(kw in text_lower for kw in keywords_high):
        return "high"
    return "low"
```

### Pattern 2: Token Cost Tracking

Track LLM costs for budgeting and billing.

```python
def analyze_contract(contract_text: str) -> Dict:
    """Analyze contract with token tracking."""
    from llm.model_factory import get_llm
    from llm.token_counter import get_token_counter
    from langchain_core.messages import HumanMessage
    
    llm = get_llm()
    tc = get_token_counter()
    
    response = llm.invoke([HumanMessage(content=f"Summarize:\n{contract_text}")])
    
    # Track this LLM call
    tc.record_from_response(response, model="gpt-4o")
    
    # Later, get totals:
    totals = tc.totals()
    print(f"Today's LLM spend: ${totals.get('total_cost_usd', 0):.2f}")
    
    return {"analysis": response.content}
```

### Pattern 3: Sanitization Before LLM

Never send raw user data to LLM. Mask PII first.

```python
async def generate_email_body(user_data: Dict) -> str:
    """Generate email with PII-safe prompting."""
    from observability.pii_sanitizer import sanitize_output
    from llm.model_factory import get_llm
    from langchain_core.messages import HumanMessage
    
    # Sanitize user data (masks email, phone, etc.)
    safe_data = sanitize_output(user_data)
    
    llm = get_llm()
    response = llm.invoke([
        HumanMessage(content=f"Draft a professional email using:\n{json.dumps(safe_data)}")
    ])
    
    return response.content
```

### Pattern 4: Using Specific LLM for Specific Tasks

Different tasks benefit from different models:

```python
def classify_sentiment(text: str) -> str:
    """Quick sentiment (use fast Groq)."""
    llm = get_llm(prefer="groq", temperature=0.0)
    prompts = [HumanMessage(content=f"Sentiment of: {text}\nReply: positive|negative|neutral")]
    return llm.invoke(prompts).content

def generate_business_strategy(market_data: str) -> str:
    """Complex analysis (use powerful OpenAI)."""
    llm = get_llm(prefer="openai", temperature=0.5)  # Slight creativity allowed
    prompts = [HumanMessage(content=f"Generate strategy:\n{market_data}")]
    return llm.invoke(prompts).content

def fallback_summary(contract_text: str) -> str:
    """Simple task, always works (use local Ollama)."""
    llm = get_llm(prefer="ollama", temperature=0.0)
    prompts = [HumanMessage(content=f"Summarize in 2 lines:\n{contract_text}")]
    return llm.invoke(prompts).content
```

---

## 13.8 Running Full Project: All Components Together

### Prerequisites & Installation

```bash
# 1. System requirements
python3 --version  # Need 3.11+
which openai  # or `ollama`, or set API keys

# 2. Install Ollama (for local LLM fallback)
# macOS/Linux:
curl https://ollama.ai/install.sh | sh

# 3. Start Ollama in background
ollama serve &

# 4. Pull a model (first time takes ~5 min)
ollama pull qwen2.5:3b

# Verify Ollama is running:
curl http://localhost:11434/api/tags  # Should return model list
```

### Setup & Start

```bash
# Clone and enter project
git clone <repository_url> piloth
cd piloth

# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate  # or: .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp config/.env.example .env
# Edit .env if using OpenAI/Groq:
#   OPENAI_API_KEY=sk-...
#   GROQ_API_KEY=gsk_...
# Leave blank to use Ollama only (recommended for getting started)
```

### Terminal 1: API Server

```bash
source .venv/bin/activate
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Expected output:
# ✓ Database initialized
# ✓ Agents registered: vendor_management, communication, ...
# ✓ LLM provider: ollama (or openai/groq if configured)
# ✓ Task Queue started with 5 workers
# INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2: Check API Health

```bash
curl http://localhost:8000/health

# Expected:
# {
#   "status": "ok",
#   "database": "connected",
#   "llm_provider": "ollama",
#   "llm_reachable": true,
#   "task_queue": "running"
# }
```

### Terminal 3: WebSocket Client (Live Updates)

```bash
python3 << 'EOF'
import asyncio, websockets, json, time

async def ws_listener():
    try:
        uri = "ws://localhost:8000/ws?session_id=demo-session"
        async with websockets.connect(uri) as ws:
            print("📡 WebSocket connected. Waiting for messages...")
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                print(f"📨 {data.get('component_type', '?')}: {json.dumps(data, indent=2)[:200]}...")
    except Exception as e:
        print(f"❌ {e}")

asyncio.run(ws_listener())
EOF
```

### Terminal 4: Test a Request

```bash
# Example 1: Vendor Management
curl -X POST http://localhost:8000/agents/vendor_management/run \
  -H "Content-Type: application/json" \
  -d '{
    "action": "find_best",
    "service_tags": ["cloud_infrastructure"],
    "budget_usd": 50000
  }'

# Example 2: Check task status
curl http://localhost:8000/tasks/abcd-1234-efgh-5678

# Example 3: List pending approvals
curl http://localhost:8000/hitl/pending
```

### Running Tests

```bash
# Unit tests (all vendors, meetings agents)
.venv/bin/python3 tests/test_vendor_management.py
.venv/bin/python3 tests/test_meetings_agent.py

# Integration test (full flow)
.venv/bin/python3 << 'EOF'
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integrations.data_warehouse.sqlite_client import init_db
from backend.services.agent_registry import initialise_agents
from config.settings import Settings

# Initialize
init_db()
settings = Settings()
initialise_agents(settings)

# Test orchestrator
from orchestrator.controller import OrchestratorController
controller = OrchestratorController(settings)

result = controller.handle(
    message="Show me the best cloud vendors for $50k",
    session_id="test-session-1"
)

print(f"✓ Orchestrator handled request")
print(f"  Agent: {result['intent']['agent']}")
print(f"  Action: {result['intent']['action']}")
print(f"  Status: {result['result'].get('status', 'unknown')}")
EOF
```

### Monitoring & Debugging

**View task queue status:**

```bash
sqlite3 pilot_db.sqlite "SELECT COUNT(*) as total, status, COUNT(status) as count FROM task_queue GROUP BY status;"
```

**View approval history:**

```bash
sqlite3 pilot_db.sqlite "SELECT task_id, agent_name, status, feedback FROM hitl_approvals ORDER BY created_at DESC LIMIT 10;"
```

**View LLM logs:**

```bash
# Tail logs for LLM provider selection
tail -f /tmp/piloth.log | grep "\[LLM\]"
```

**Reset everything:**

```bash
# Delete database (all data lost)
rm -f pilot_db.sqlite

# Restart server (will re-seed)
uvicorn backend.api.main:app --reload
```

---

## 14. Design Principles

### 1. Strict Separation of Concerns

| Layer | Where | What It Does | What It Must NOT Do |
|---|---|---|---|
| DAL | `integrations/data_warehouse/*.py` | Execute SQL | Business logic, LLM calls |
| Tool | `agents/*/tools/*.py` | One task: call DAL or external API | Execute SQL directly |
| Node | `agents/*/nodes/*.py` | Orchestrate tools, update state | Call external APIs directly |
| Graph | `agents/*/graph.py` | Wire nodes together | Any business logic |
| Agent | `agents/*/agent.py` | Validate input/output, invoke graph | No SQL, no LLM calls |
| API Route | `backend/api/routes/*.py` | HTTP I/O | Any business logic |

### 2. LLM Calls Always Have Fallbacks

Every tool or node that calls an LLM must also implement a rule-based or heuristic fallback:

```python
try:
    result = call_llm(prompt)
except Exception:
    result = rule_based_fallback(data)   # ← never let the agent crash
```

### 3. All Data is Replaceable

Mock data is seeded via `init_db()`. Every mock call has a clearly marked comment:

```python
# PRODUCTION: Replace with real API call:
# from external_sdk import Client
# client = Client(api_key=os.environ["API_KEY"])
# return client.fetch(...)
```

### 4. Human-in-the-Loop for High-Risk Actions

Use `NodeInterrupt` for any action that:
- Sends an external communication (email, Slack)
- Creates a calendar event with external attendees
- Spends company money
- Deletes data

Pattern in any node:

```python
if state.get("requires_approval"):
    from langgraph.errors import NodeInterrupt
    raise NodeInterrupt("Human approval required: describe what needs approval.")
```

Then compile the graph with `interrupt_after=["node_name"]` and a checkpointer.

### 5. Token Tracking Everywhere

Import the counter anywhere and record usage after LLM calls:

```python
from llm.token_counter import get_token_counter
tc = get_token_counter()
response = llm.invoke(messages)
tc.record_from_response(response, model="gpt-4o")
```

---

## 15. Command Reference & Troubleshooting

### Quick Start Commands

```bash
# One-command setup (automatic venv + install + db)
bash quick_start.sh

# OR step-by-step:
make setup
make run-dev
# In another terminal: make healthcheck
```

### Using Make (Recommended)

All commands below can run via `make`:

```bash
make help              # Show all commands
make setup             # Install + init DB
make install           # Install dependencies only
make run               # Production server
make run-dev           # Development server with reload
make test              # Run all tests (both agents)
make test-vendor       # Vendor Management tests (35 tests)
make test-meetings     # Communication Agent tests (41 tests)
make healthcheck       # Check API + LLM connectivity
make db-init           # Initialize + seed database
make db-reset          # DELETE database (warning!)
make db-query          # Open SQLite shell
make db-shell          #Alias for db-query
make clean             # Clean temp files
make lint              # Run code linting
make format            # Format code with black
make demo              # Run end-to-end demo
```

### Manual Commands

```bash
# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env
cp config/.env.example .env

# Initialize database
python3 << 'EOF'
from integrations.data_warehouse.sqlite_client import init_db
init_db(seed=True)
EOF

# Start API server
uvicorn backend.api.main:app --reload --port 8000

# Run tests (in another terminal)
python3 tests/test_vendor_management.py
python3 tests/test_meetings_agent.py

# Check health
curl http://localhost:8000/health

# Reset database
rm -f pilot_db.sqlite
```

### API Testing

```bash
# Check server health
curl http://localhost:8000/health

# Test vendor management agent
curl -X POST http://localhost:8000/agents/vendor_management/run \
  -H "Content-Type: application/json" \
  -d '{
    "action": "find_best",
    "service_tags": ["cloud_infrastructure"],
    "budget_usd": 50000
  }'

# Get task status
curl http://localhost:8000/tasks/{task_id}

# Get pending approvals
curl http://localhost:8000/hitl/pending

# Approve a task
curl -X POST http://localhost:8000/hitl/decision \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "abc-123",
    "approved": true,
    "feedback": "Looks good"
  }'
```

### WebSocket Testing

```bash
# Python WebSocket listener (Terminal 1)
pip install websocket-client
python3 << 'EOF'
import asyncio
import websockets
import json

async def listen():
    async with websockets.connect("ws://localhost:8000/ws?session_id=test") as ws:
        while True:
            msg = json.loads(await ws.recv())
            print(f"Received: {msg['component_type']}")
            
asyncio.run(listen())
EOF

# Make a request (Terminal 2)
curl -X POST http://localhost:8000/agents/vendor_management/run \
  -H "Content-Type: application/json" \
  -d '{"action":"find_best","service_tags":["cloud"],"budget_usd":50000}'

# Watch progress in Terminal 1
# Output:
# Received: agent_progress
# Received: agent_progress
# Received: task_complete
```

### Database Management

```bash
# View all tasks
sqlite3 pilot_db.sqlite "SELECT task_id, status, agent_name FROM task_queue LIMIT 10;"

# View approval history
sqlite3 pilot_db.sqlite "SELECT task_id, status, feedback FROM hitl_approvals ORDER BY created_at DESC LIMIT 5;"

# View vendor data
sqlite3 pilot_db.sqlite "SELECT name, financial_health FROM vendors LIMIT 5;"

# Count records
sqlite3 pilot_db.sqlite "SELECT 'tasks' as table_name, COUNT(*) as count FROM task_queue UNION ALL SELECT 'approvals', COUNT(*) FROM hitl_approvals;"

# Clear all data (except schema)
sqlite3 pilot_db.sqlite "DELETE FROM task_queue; DELETE FROM hitl_approvals; DELETE FROM agent_feedback;"
```

### Troubleshooting

**Problem: "Cannot connect to Ollama"**

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it:
ollama serve &

# Pull a model
ollama pull qwen2.5:3b

# Verify
curl http://localhost:11434/api/tags
```

**Problem: "Database is locked"**

```bash
# Kill any existing connections and reset
rm -f pilot_db.sqlite pilot_db.sqlite-*

# Restart server
uvicorn backend.api.main:app --reload
```

**Problem: "ModuleNotFoundError: No module named 'agents'"**

```bash
# Make sure you're in venv
source .venv/bin/activate

# Make sure you're in project root
cd /path/to/PilotH

# Reinstall in editable mode
pip install -e .
```

**Problem: "OpenAI API key not found"**

```bash
# Option 1: Set in .env
OPENAI_API_KEY=sk-...

# Option 2: Set in shell
export OPENAI_API_KEY=sk-...

# Option 3: Use Ollama (default, no key needed)
# Leave .env as-is, will auto-use ollama
```

**Problem: "LLM request too slow"**

```bash
# Switch to Groq (fastest inference)
# In .env:
LLM_PRIMARY=groq
GROQ_API_KEY=gsk_...

# Or force Ollama with smaller model
OLLAMA_MODEL=neural-chat  # lighter than qwen2.5:3b

# Check what models are available
ollama list
```

### Performance Tuning

```bash
# Increase task workers (handle more concurrent tasks)
# In config/settings.py:
task_queue_max_workers: int = 10  # instead of default 5

# Enable aggressive caching
# In any agent node:
from memory.global_context import get_global_context
ctx = get_global_context()
ctx.set("vendor_cache", all_vendors, ttl_seconds=3600)

# Monitor LLM costs
# In any tool:
from llm.token_counter import get_token_counter
tc = get_token_counter()
totals = tc.totals()
print(f"LLM cost so far: ${totals['total_cost_usd']}")
```

### Log Files & Debugging

```bash
# View live logs (if logger sends to file)
tail -f /tmp/piloth.log

# Enable debug logging
# In .env:
DEBUG=true

# Verbose LLM logging
# In your code:
import logging
logging.getLogger("langchain").setLevel(logging.DEBUG)

# Print all LLM calls
# In your node:
from observability.pii_sanitizer import sanitize_for_logging
print(f"Debug: {sanitize_for_logging(payload)}")
```

### Docker Deployment (Optional)

```bash
# Build image
docker build -t piloth:latest .

# Run container
docker run -p 8000:8000 -e OPENAI_API_KEY=$OPENAI_API_KEY piloth:latest

# Or with docker-compose
docker-compose up

# Check logs
docker logs <container_id>
```

---

## 16. Common Issues & Solutions

| Problem | Solution |
|---|---|
| Import errors (`ModuleNotFoundError`) | Run: `source .venv/bin/activate` and `pip install -r requirements.txt` |
| Database locked | Run: `rm -f pilot_db.sqlite` and restart server |
| Ollama connection refused | Run: `ollama serve &` in background terminal |
| LLM latency (slow responses) | Switch to Groq or smaller Ollama model |
| Approval not showing in UI | Check WebSocket is connected; check `hitl_threshold` in `.env` |
| Task stuck in "running" | Kill server, check database, restart |
| PII not being masked | Verify `enable_pii_sanitization=True` in TaskQueueManager |
| Out of memory | Reduce `task_queue_max_workers` or increase VM RAM |

---

## 17. Contributing & Next Steps

### How to Contribute

1. **Add a new agent**: Follow [Section 6](#6-how-to-add-a-new-agent--step-by-step)
2. **Add a tool**: Follow [Section 7](#7-how-to-add-a-new-tool-to-an-existing-agent)
3. **Add a database table**: Follow [Section 9](#9-how-to-add-new-database-tables)
4. **Fix a bug**: Open an issue; submit a PR with tests

### Roadmap

- [ ] Multi-turn conversation support (chat history)
- [ ] Fine-tuned models for specific domains
- [ ] GraphQL API (in addition to REST)
- [ ] Real-time collaboration (multiple users same session)
- [ ] Mobile app (React Native / Flutter)
- [ ] Advanced analytics dashboard
- [ ] Compliance audit logging

---

*PilotH — Enterprise-grade multi-agent orchestration. Simple concepts. Production-ready. Infinitely extensible.*