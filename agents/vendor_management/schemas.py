"""
Pydantic schemas and LangGraph state for the Vendor Management Agent.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict, Annotated, Union
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VendorAction(str, Enum):
    SEARCH_VENDORS = "search_vendors"  # Browse/list vendors across services or categories
    FIND_BEST = "find_best"  # Match best vendor(s) for a new project requirement
    EVALUATE = "evaluate"  # Score & assess a specific existing vendor
    MONITOR_SLA = "monitor_sla"  # Check SLA compliance
    TRACK_MILESTONES = "track_milestones"  # Review milestone status
    SUMMARIZE_CONTRACT = "summarize_contract"  # Parse and summarize contract terms
    GAP_ANALYSIS = "gap_analysis" # Identify unmet capabilities
    FULL_ASSESSMENT = "full_assessment"  # Combination of all of the above


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Agent input
# ---------------------------------------------------------------------------


class VendorManagementInput(BaseModel):
    """
    Unified input schema for the Vendor Management Agent.

    For FIND_BEST action:
        - service_required is mandatory
        - vendor_name / vendor_id are ignored

    For other actions:
        - vendor_name or vendor_id is mandatory
    """

    action: Union[VendorAction, str] = Field(
        default=VendorAction.FULL_ASSESSMENT, description="What the agent should do"
    )

    # --- Existing vendor context (EVALUATE, MONITOR_SLA, TRACK_MILESTONES, FULL_ASSESSMENT)
    vendor_name: Optional[str] = Field(
        None, description="Name (or partial) of the vendor"
    )
    vendor_id: Optional[str] = Field(
        None, description="Internal vendor ID (e.g. V-001)"
    )

    # --- New project / service matching (FIND_BEST)
    service_required: Optional[str] = Field(
        None, description="Service tag needed (e.g. cloud_hosting)"
    )
    industry: Optional[str] = Field(
        None, description="Industry filter (e.g. Technology, Finance)"
    )
    budget_monthly: Optional[float] = Field(
        None, description="Max monthly budget in USD"
    )
    category: Optional[str] = Field(
        None, description="Category filter (e.g. IT Services, Logistics)"
    )
    min_quality_score: float = Field(75.0, ge=0, le=100)
    min_on_time_rate: float = Field(0.85, ge=0, le=1.0)
    tier: Optional[str] = Field(
        None, description="preferred | standard | trial"
    )
    contract_status: Optional[str] = Field(
        None, description="active | expired | pending"
    )
    country: Optional[str] = Field(None, description="Country ISO code (e.g. US)")
    client_project_id: Optional[str] = Field(
        None, description="Client project ID for persisting result"
    )
    top_n: int = Field(5, ge=1, le=20)

    # --- Multi-Agent Context
    context_history: Dict[str, Any] = Field(default_factory=dict, description="Results from previous agents in the chain")
    step_reasoning: Optional[str] = Field(None, description="Instruction from the planner for this specific step")

    # --- Other
    contract_reference: Optional[str] = Field(None)
    project_id: Optional[str] = Field(None)

    class Config:
        use_enum_values = True
        extra = "allow"


# ---------------------------------------------------------------------------
# Agent output
# ---------------------------------------------------------------------------


class RiskItem(BaseModel):
    category: str
    description: str
    severity: str  # high | medium | low
    mitigation: Optional[str]


from orchestrator.schemas import AgentOutput


class VendorManagementOutput(AgentOutput):
    """
    Output schema for Vendor Management Agent.
    Inherits standard fields (action_performed, llm_summary, thought, data, suggestions, requires_human_review, error).
    """

    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None

    # For SEARCH_VENDORS
    vendors: List[Dict[str, Any]] = Field(default_factory=list)

    # For FIND_BEST
    ranked_vendors: List[Dict[str, Any]] = Field(default_factory=list)
    comparison_matrix: List[Dict[str, Any]] = Field(default_factory=list)
    top_recommendation: Optional[str] = None  # vendor_id

    # For assessment
    overall_score: Optional[float] = Field(None, ge=0, le=100)
    sla_compliance: Optional[float] = Field(None, ge=0, le=100)
    evaluation_breakdown: Dict[str, float] = Field(default_factory=dict)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# LangGraph internal state
# ---------------------------------------------------------------------------


class VendorState(TypedDict):
    """
    State schema for the Vendor Management workflow.
    Enhanced with thinking and dynamic tool-call support.
    """

    # --- Core Input ---
    action: str  # find_best | evaluate | monitor_sla | etc.
    messages: Annotated[List[BaseMessage], add_messages]
    context_history: Dict[str, Any]  # Map of prev_agent -> result
    step_reasoning: Optional[str]

    # --- Strategic Context (Reasoning) ---
    thought: Optional[str]  # The <think> block content
    next_step: Optional[str]  # routing hint

    # --- Entities ---
    vendor_id: Optional[str]
    vendor_name: Optional[str]
    service_required: Optional[str]
    industry: Optional[str]
    budget_monthly: Optional[float]
    min_quality_score: float
    min_on_time_rate: float
    tier: Optional[str]
    contract_status: Optional[str]
    country: Optional[str]
    client_project_id: Optional[str]
    top_n: int
    contract_reference: Optional[str]
    project_id: Optional[str]

    # ---- Intermediate state populated by nodes ---
    vendors: List[Dict[str, Any]]
    vendor_records: List[Dict[str, Any]]  # from vendor_search / vendor_matcher
    ranked_vendors: List[Dict[str, Any]]  # scored candidates
    comparison_matrix: List[Dict[str, Any]] # tabular analysis
    top_recommendation: Optional[str]
    vendor_details: Dict[str, Any]  # single vendor full record
    sla_data: Dict[str, Any]
    milestone_data: List[Dict[str, Any]]
    contract_data: Dict[str, Any]
    evaluation_scores: Dict[str, float]
    risk_items: List[Dict[str, str]]
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    overall_score: Optional[float]
    sla_compliance: Optional[float]
    reflection: Optional[Dict[str, Any]]
    llm_summary: Optional[str]
    requires_human_review: bool
    error: Optional[str]
