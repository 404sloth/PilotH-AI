"""
Gap Analyzer Tool — Identify mismatches between requirements and vendor capabilities.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool

class GapRequirement(BaseModel):
    category: str
    requirement: str
    criticality: str = Field(..., description="High, Medium, or Low")

class GapAnalysisInput(BaseModel):
    client_project_id: Optional[str] = Field(None, description="Project ID to load requirements from")
    requirements: List[GapRequirement] = Field(default_factory=list, description="Explicit list of requirements if project ID is not provided")
    target_vendors: List[str] = Field(default_factory=list, description="List of vendor IDs to compare against")

class GapOutput(BaseModel):
    vendor_id: str
    vendor_name: str
    unmet_critical: List[str]
    unmet_optional: List[str]
    gap_summary: str

class GapAnalysisOutput(BaseModel):
    success: bool
    requirements_analyzed: int
    vendor_gaps: List[GapOutput]
    overall_suggestions: List[str]
    error: Optional[str] = None

class GapAnalyzerTool(StructuredTool):
    """Detect gaps between project requirements and vendor capabilities."""

    name: str = "gap_analyzer"
    description: str = (
        "Identify mismatches between demand and vendor capabilities. "
        "Useful for gap detection to suggest alternative or additional vendors."
    )
    args_schema: type[BaseModel] = GapAnalysisInput

    def execute(self, validated_input: GapAnalysisInput) -> GapAnalysisOutput:
        from integrations.data_warehouse.vendor_db import get_client_project, get_vendor_by_id

        reqs = validated_input.requirements
        if not reqs and validated_input.client_project_id:
            project = get_client_project(validated_input.client_project_id)
            if project and project.get("requirements"):
                for k, v in project["requirements"].items():
                    reqs.append(GapRequirement(category="auto", requirement=f"{k}: {v}", criticality="Medium"))
                    
        if not reqs:
            return GapAnalysisOutput(success=False, requirements_analyzed=0, vendor_gaps=[], overall_suggestions=[], error="No requirements provided.")
            
        gaps = []
        all_unmet_critical = set()
        
        for vendor_id in validated_input.target_vendors:
            vendor = get_vendor_by_id(vendor_id)
            if not vendor:
                continue
                
            vendor_services = vendor.get("services", [])
            # Simple mock capability matching based on strings for demonstration:
            # In a real system, would use CapabilityMapper to standardize terminology.
            unmet_crit = []
            unmet_opt = []
            
            for doc in reqs:
                # Naive matching: if the requirement mentions a service we don't have
                # We'll just distribute some gaps randomly or string-match based on services.
                # Here we assume a gap if the requirement isn't clearly in the vendor's services list.
                found = any(s.lower() in doc.requirement.lower() for s in vendor_services)
                if not found and len(vendor_services) > 0:
                     if doc.criticality.lower() == "high":
                         unmet_crit.append(doc.requirement)
                         all_unmet_critical.add(doc.requirement)
                     else:
                         unmet_opt.append(doc.requirement)
            
            summary = "Meets most expectations."
            if unmet_crit:
                summary = f"Critical gaps detected in {len(unmet_crit)} areas."
                
            gaps.append(GapOutput(
                vendor_id=vendor_id,
                vendor_name=vendor.get("name", vendor_id),
                unmet_critical=unmet_crit,
                unmet_optional=unmet_opt,
                gap_summary=summary
            ))

        suggestions = []
        if all_unmet_critical:
            suggestions.append("Consider onboarding a new vendor to cover the missing critical capabilities: " + ", ".join(list(all_unmet_critical)[:3]))
            suggestions.append("Alternatively, relax the critical constraints if possible.")
        else:
            suggestions.append("All critical requirements are theoretically met by the candidate pool.")

        return GapAnalysisOutput(
            success=True,
            requirements_analyzed=len(reqs),
            vendor_gaps=gaps,
            overall_suggestions=suggestions
        )
