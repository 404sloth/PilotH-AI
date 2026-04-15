"""
LLM Query Orchestrator for Vendor Requirements.

Intelligently parses natural language client requirements and converts them
into structured vendor matching parameters.

Example queries:
  - "Find cloud hosting vendors under $1k/month with >95% uptime"
  - "I need a data analytics vendor that's good with real-time processing"
  - "Looking for preferred tier vendors for CI/CD in US with <$5k/month"
  - "Need reliable vendors for backup & DR with excellent SLA track record"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage

from observability.logger import get_logger
from observability.metrics import get_metrics
from observability.tracing import get_tracer
from observability.pii_sanitizer import sanitize_data

logger = logging.getLogger(__name__)
otel_logger = get_logger("vendor.query_orchestrator")


@dataclass
class ParsedVendorRequirements:
    """Structured vendor requirements from natural language."""
    service_tag: str
    budget_monthly: Optional[float] = None
    min_quality_score: float = 75.0
    min_on_time_rate: float = 0.85
    min_avg_client_rating: float = 4.0
    required_tier: Optional[str] = None
    country: Optional[str] = None
    additional_criteria: Dict[str, Any] = None
    confidence: float = 0.5
    requires_clarification: bool = False
    clarification_request: str = ""
    
    def to_matcher_input(self) -> Dict[str, Any]:
        """Convert to VendorMatcherInput dict."""
        return {
            "service_tag": self.service_tag,
            "budget_monthly": self.budget_monthly,
            "min_quality_score": self.min_quality_score,
            "min_on_time_rate": self.min_on_time_rate,
            "min_avg_client_rating": self.min_avg_client_rating,
            "required_tier": self.required_tier,
            "country": self.country,
            "top_n": 5,
        }


class VendorQueryOrchestrator:
    """
    Converts natural language vendor queries into structured requirements.
    
    Flow:
      1. Parse query with LLM
      2. Extract service type, budget, quality criteria
      3. Identify country/tier preferences
      4. Validate requirements
      5. Return structured params for VendorMatcherTool
    """

    def __init__(self):
        """Initialize orchestrator."""
        self.tracer = get_tracer("vendor_management")
        self.metrics = get_metrics()

    def parse_vendor_query(
        self,
        query: str,
    ) -> ParsedVendorRequirements:
        """
        Parse natural language vendor requirement query.
        
        Args:
            query: Natural language query string
            
        Returns:
            ParsedVendorRequirements with structured parameters
        """
        with self.tracer.trace_operation(
            "vendor_query_parsing",
            attributes={"query_length": len(query)}
        ) as span:
            otel_logger.info(
                "Parsing vendor requirement query",
                agent="vendor_management",
                action="query_parse",
                data={"query_length": len(query)},
            )

            sanitized_query = sanitize_data(query)

            try:
                # Use LLM to parse requirements
                parsed_req = self._parse_with_llm(query)
                span.add_event("llm_parsing_successful")
                method = "llm"
            except Exception as e:
                otel_logger.warning(
                    "LLM parsing failed, using rule-based",
                    agent="vendor_management",
                    error=str(e),
                )
                parsed_req = self._parse_with_rules(query)
                span.add_event("rule_based_parsing_used")
                method = "rules"

            self.metrics.record_histogram(
                "vendor_query.parse_confidence",
                parsed_req.confidence,
                attributes={"method": method},
            )
            self.metrics.increment_counter(
                "vendor_query.parsed",
                attributes={"method": method},
            )

            otel_logger.info(
                "Query parsing complete",
                agent="vendor_management",
                action="parse_complete",
                data={
                    "service_tag": parsed_req.service_tag,
                    "confidence": parsed_req.confidence,
                    "requires_clarification": parsed_req.requires_clarification,
                },
            )

            return parsed_req

    def _parse_with_llm(self, query: str) -> ParsedVendorRequirements:
        """
        Use LLM to parse vendor requirements.
        
        Returns:
            ParsedVendorRequirements with extracted parameters
        """
        from llm.model_factory import get_llm

        prompt = f"""Analyze this vendor requirement query and extract structured parameters.

Query: "{query}"

Extract and return JSON:
{{
    "service_tag": <service category like "cloud_hosting", "data_analytics", etc>,
    "budget_monthly": <USD amount or null>,
    "min_quality_score": <0-100, defaults 75>,
    "min_on_time_rate": <0-1, defaults 0.85>,
    "min_avg_client_rating": <1-5, defaults 4.0>,
    "required_tier": <"preferred" | "standard" | "trial" or null>,
    "country": <ISO country code or null>,
    "confidence": <0-1, how sure about service_tag>,
    "requires_clarification": <true|false>,
    "clarification_request": <specific question if unclear>,
    "additional_criteria": <dict of any other requirements>
}}

CRITICAL: service_tag must be from: cloud_hosting, data_analytics, ci_cd_pipelines, 
backup_dr, communication_platform, telecom, monitoring, database_service, api_gateway, 
security_tools, compliance_officer. Return similar if not exact match."""

        try:
            llm = get_llm(temperature=0.1)
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()

            # Clean markdown
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            parsed = json.loads(content)
            
            # Validate required field
            if not parsed.get("service_tag"):
                raise ValueError("No service_tag extracted from query")

            return ParsedVendorRequirements(
                service_tag=parsed.get("service_tag", ""),
                budget_monthly=self._parse_budget(parsed.get("budget_monthly")),
                min_quality_score=max(0, min(100, parsed.get("min_quality_score", 75))),
                min_on_time_rate=max(0, min(1, parsed.get("min_on_time_rate", 0.85))),
                min_avg_client_rating=max(1, min(5, parsed.get("min_avg_client_rating", 4.0))),
                required_tier=parsed.get("required_tier"),
                country=parsed.get("country"),
                additional_criteria=parsed.get("additional_criteria", {}),
                confidence=parsed.get("confidence", 0.5),
                requires_clarification=parsed.get("requires_clarification", False),
                clarification_request=parsed.get("clarification_request", ""),
            )

        except Exception as e:
            logger.warning(f"LLM parsing failed: {e}")
            raise

    def _parse_with_rules(self, query: str) -> ParsedVendorRequirements:
        """
        Rule-based fallback for parsing.
        
        Returns:
            ParsedVendorRequirements (may require clarification)
        """
        import re

        query_lower = query.lower()
        
        # Service tag detection
        service_map = {
            "cloud": "cloud_hosting",
            "hosting": "cloud_hosting",
            "data": "data_analytics",
            "analytics": "data_analytics",
            "cicd": "ci_cd_pipelines",
            "pipeline": "ci_cd_pipelines",
            "backup": "backup_dr",
            "dr": "backup_dr",
            "communication": "communication_platform",
            "chat": "communication_platform",
            "telecom": "telecom",
            "monitor": "monitoring",
            "database": "database_service",
            "api": "api_gateway",
            "security": "security_tools",
            "compliance": "compliance_officer",
        }
        
        detected_service = None
        for keyword, service in service_map.items():
            if keyword in query_lower:
                detected_service = service
                break

        if not detected_service:
            detected_service = "cloud_hosting"  # Default fallback

        # Budget extraction
        budget_match = re.search(r"\$?(\d+[,\d]*)/month", query_lower)
        budget = float(budget_match.group(1).replace(",", "")) if budget_match else None

        # Quality/criteria extraction
        min_quality = 75.0
        if "high" in query_lower and "quality" in query_lower:
            min_quality = 85.0
        if "excellent" in query_lower:
            min_quality = 90.0

        min_on_time = 0.85
        if "reliable" in query_lower or "uptime" in query_lower:
            min_on_time = 0.95

        min_rating = 4.0
        if "top" in query_lower or "best" in query_lower:
            min_rating = 4.5

        # Tier detection
        tier = None
        if "preferred" in query_lower:
            tier = "preferred"

        # Country detection
        country = None
        if "us" in query_lower or "usa" in query_lower:
            country = "US"
        elif "europe" in query_lower or "eu" in query_lower:
            country = "EU"

        return ParsedVendorRequirements(
            service_tag=detected_service,
            budget_monthly=budget,
            min_quality_score=min_quality,
            min_on_time_rate=min_on_time,
            min_avg_client_rating=min_rating,
            required_tier=tier,
            country=country,
            confidence=0.6,
            requires_clarification=not detected_service,
            clarification_request=(
                "Could you specify which service you need? "
                "(e.g., cloud hosting, data analytics, CI/CD)"
            ) if not detected_service else "",
        )

    def _parse_budget(self, budget_value: Any) -> Optional[float]:
        """Parse budget value from various formats."""
        if not budget_value:
            return None
        if isinstance(budget_value, (int, float)):
            return float(budget_value)
        if isinstance(budget_value, str):
            import re
            match = re.search(r"(\d+[,\d]*)", budget_value)
            if match:
                return float(match.group(1).replace(",", ""))
        return None

    def generate_clarification_request(
        self,
        parsed_req: ParsedVendorRequirements,
    ) -> str:
        """Generate clarification message if requirements are ambiguous."""
        if parsed_req.requires_clarification:
            return (
                f"I'm looking for: {parsed_req.service_tag}\n\n"
                f"Could you clarify:\n"
                f"- Budget: {parsed_req.budget_monthly or 'not specified'}\n"
                f"- Quality requirement: {parsed_req.min_quality_score}\n"
                f"- Reliability: {parsed_req.min_on_time_rate * 100:.0f}% on-time\n\n"
                f"{parsed_req.clarification_request}"
            )
        return ""

    def validate_requirements(
        self,
        parsed_req: ParsedVendorRequirements,
    ) -> tuple:
        """
        Validate parsed requirements.
        
        Returns:
            (is_valid, error_message)
        """
        if not parsed_req.service_tag:
            return False, "Service tag is required"
        
        if parsed_req.min_quality_score < 0 or parsed_req.min_quality_score > 100:
            return False, "Quality score must be 0-100"
        
        if parsed_req.min_on_time_rate < 0 or parsed_req.min_on_time_rate > 1:
            return False, "On-time rate must be 0-1"
        
        if parsed_req.min_avg_client_rating < 1 or parsed_req.min_avg_client_rating > 5:
            return False, "Client rating must be 1-5"
        
        if parsed_req.budget_monthly and parsed_req.budget_monthly < 0:
            return False, "Budget must be positive"
        
        return True, ""


# Global orchestrator instance
_orchestrator: Optional[VendorQueryOrchestrator] = None


def get_vendor_query_orchestrator() -> VendorQueryOrchestrator:
    """Get or create the global orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = VendorQueryOrchestrator()
    return _orchestrator
