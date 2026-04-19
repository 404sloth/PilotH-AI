"""
Vendor Management Agent — orchestrates the full LangGraph workflow.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from config.settings import Settings
from human_loop.manager import HITLManager

from .schemas import VendorManagementInput, VendorManagementOutput, VendorState
from .graph import build_vendor_graph
from .tools import (
    VendorSearchTool,
    VendorMatcherTool,
    ContractParserTool,
    SLAMonitorTool,
    MilestoneTrackerTool,
    VendorScorecardTool,
)
from .tools.agreement_expiry_tracker import AgreementExpiryTool
from .tools.risk_assessment import VendorRiskAssessmentTool
from .tools.financial_analyzer import VendorFinancialTool
from .tools.kb_search import KnowledgeBaseSearchTool


class VendorManagementAgent(BaseAgent):
    """
    Vendor Management Agent.

    Capabilities:
    ─────────────
    • find_best       — compare all vendors offering a service, rank by project fit
    • evaluate        — score a specific vendor across key dimensions (via LLM)
    • monitor_sla     — check SLA compliance and breaches
    • track_milestones— analyse project milestone health and delays
    • full_assessment — run the complete pipeline for a single vendor
    """

    name: str = "vendor_management"

    def __init__(
        self,
        config: Settings,
        tool_registry=None,
        hitl_manager: Optional[HITLManager] = None,
    ):
        super().__init__(config, tool_registry, hitl_manager)
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all vendor management tools with the shared tool registry."""
        if not self.tool_registry:
            return
        for tool in [
            VendorSearchTool(),
            VendorMatcherTool(),
            ContractParserTool(),
            SLAMonitorTool(),
            MilestoneTrackerTool(),
            VendorScorecardTool(),
            AgreementExpiryTool(),
            VendorRiskAssessmentTool(),
            VendorFinancialTool(),
            KnowledgeBaseSearchTool(),
        ]:
            self.tool_registry.register_tool(tool, self.name)

    # ------------------------------------------------------------------
    # Schema declarations
    # ------------------------------------------------------------------
    @property
    def input_schema(self) -> Type[BaseModel]:
        return VendorManagementInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return VendorManagementOutput

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------
    def get_subgraph(self):
        return build_vendor_graph(
            llm_with_tools=self.llm_with_tools,
            tools=self.tools,
            hitl_manager=self.hitl,
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the vendor management workflow with full Pydantic validation.

        Args:
            input_data: Raw dict matching VendorManagementInput schema

        Returns:
            Validated dict matching VendorManagementOutput schema
        """
        validated_in = VendorManagementInput(**input_data)

        # Map to LangGraph state
        state_input: Dict[str, Any] = {
            "action": validated_in.action,
            "vendor_name": validated_in.vendor_name,
            "vendor_id": validated_in.vendor_id,
            "service_required": validated_in.service_required,
            "industry": validated_in.industry,
            "budget_monthly": validated_in.budget_monthly,
            "min_quality_score": validated_in.min_quality_score,
            "min_on_time_rate": validated_in.min_on_time_rate,
            "required_tier": validated_in.required_tier,
            "country": validated_in.country,
            "client_project_id": validated_in.client_project_id,
            "top_n": validated_in.top_n,
            "contract_reference": validated_in.contract_reference,
            "project_id": validated_in.project_id,
            "messages": [],
        }

        graph = self.get_subgraph()
        result: VendorState = graph.invoke(state_input)

        # Map result → output schema
        output_data: Dict[str, Any] = {
            "action_performed": validated_in.action,
            "vendor_id": result.get("vendor_id"),
            "vendor_name": result.get("vendor_details", {}).get("name")
            or validated_in.vendor_name,
            "vendors": result.get("vendors", []),
            "ranked_vendors": result.get("ranked_vendors", []),
            "top_recommendation": result.get("top_recommendation"),
            "overall_score": result.get("overall_score"),
            "sla_compliance": result.get("sla_compliance"),
            "evaluation_breakdown": result.get("evaluation_scores", {}),
            "strengths": result.get("strengths", []),
            "weaknesses": result.get("weaknesses", []),
            "risks": result.get("risk_items", []),
            "recommendations": result.get("recommendations", []),
            "llm_summary": result.get("llm_summary"),
            "requires_human_review": result.get("requires_human_review", False),
            "error": result.get("error"),
        }

        return self.validate_output(output_data)
