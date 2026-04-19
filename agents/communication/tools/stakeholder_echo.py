"""Stakeholder Echo Tool — Personalized intelligence reporting for different stakeholders."""

import json
from typing import Dict, List, Optional, Type
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool
from langchain_core.runnables import RunnableConfig


class StakeholderEchoInput(BaseModel):
    raw_intelligence: str = Field(..., description="The main data or summary to transform")
    target_stakeholder: str = Field(..., description="CFO|CTO|Legal|Eng|Product")
    tone: str = Field("professional", description="Tone of the summary")


class StakeholderEchoOutput(BaseModel):
    personalized_summary: str
    impact_level: str
    key_takeaways: List[str]
    suggested_next_steps: List[str]


class StakeholderEchoTool(StructuredTool):
    name: str = "stakeholder_echo"
    description: str = "Refine and persona-shift intelligence reports for specific enterprise stakeholders (e.g., CFO and CTO versions)."
    args_schema: Type[BaseModel] = StakeholderEchoInput

    def execute(self, inp: StakeholderEchoInput, config: Optional[RunnableConfig] = None) -> StakeholderEchoOutput:
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = f"""Task: Transform the following intelligence into a briefing for the {inp.target_stakeholder}.
        
Intelligence:
{inp.raw_intelligence}

Tone: {inp.tone}

Requirements:
1. FOCUS: {self._get_persona_focus(inp.target_stakeholder)}
2. FORMAT: Executive bullets.
3. OUTPUT: JSON block with keys: summary, impact, takeaways (list), steps (list)."""

        try:
            llm = get_llm(temperature=0.3)
            # Use specific system instructions for persona shifting
            system_msg = SystemMessage(content=f"You are an Executive Intelligence Officer specialized in briefing {inp.target_stakeholder}s.")
            
            resp = llm.invoke([system_msg, HumanMessage(content=prompt)], config=config).content.strip()
            # Basic JSON extraction
            if "```json" in resp:
                resp = resp.split("```json")[1].split("```")[0]
            elif "```" in resp:
                resp = resp.split("```")[1].split("```")[0]
            
            data = json.loads(resp)
            return StakeholderEchoOutput(
                personalized_summary=data.get("summary", ""),
                impact_level=data.get("impact", "High"),
                key_takeaways=data.get("takeaways", []),
                suggested_next_steps=data.get("steps", [])
            )
        except Exception as e:
            return StakeholderEchoOutput(
                personalized_summary=f"Briefing for {inp.target_stakeholder}: " + inp.raw_intelligence[:100] + "...",
                impact_level="Medium",
                key_takeaways=["Analyze current findings", "Schedule stakeholder review"],
                suggested_next_steps=["Contact agent for detailed breakdown"]
            )

    def _get_persona_focus(self, persona: str) -> str:
        focus_map = {
            "CFO": "Financial stability, ROI, cost impact, and contract risks.",
            "CTO": "Technical scalability, architecture fit, performance metrics, and security.",
            "Legal": "Compliance, liability, clause interpretation, and intellectual property.",
            "Eng": "API quality, Documentation, implementation effort, and CI/CD compatibility.",
            "Product": "Feature velocity, user experience, market differentiation, and delivery timelines."
        }
        return focus_map.get(persona, "General executive summary.")
