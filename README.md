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
| Vendor Management | `vendor_management` | Best-fit ranking, SLA monitoring, contract parsing, scorecard |
| Meetings & Communication | `meetings_communication` | Smart scheduling, summarization, briefings, sentiment, follow-ups |

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
ollama pull llama3
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
OLLAMA_MODEL=llama3

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

*PilotH — Built for extensibility. Every layer designed to be swapped, every integration designed to be replaced.*