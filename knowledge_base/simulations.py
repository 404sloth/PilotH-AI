"""
Interactive Simulations — Realistic vendor management scenarios and responses.

Provides:
  - Contract negotiation simulations
  - Performance escalation scenarios
  - Budget planning exercises
  - Vendor selection decision simulations
  - SLA violation response flows
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SimulationScenario:
    """Represents an interactive simulation scenario."""
    
    def __init__(self, scenario_id: str, title: str, description: str):
        self.scenario_id = scenario_id
        self.title = title
        self.description = description
        self.steps: List[Dict[str, Any]] = []
        self.created_at = datetime.now().isoformat()
    
    def add_step(
        self,
        step_num: int,
        title: str,
        situation: str,
        options: List[str],
        expected_outcome: str,
    ) -> None:
        """Add a step to the simulation."""
        self.steps.append({
            "step": step_num,
            "title": title,
            "situation": situation,
            "options": options,
            "expected_outcome": expected_outcome,
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "steps": self.steps,
            "total_steps": len(self.steps),
            "created_at": self.created_at,
        }


class InteractiveSimulator:
    """Run interactive vendor management simulations."""
    
    def __init__(self):
        self.scenarios = {}
        self._init_scenarios()
    
    def _init_scenarios(self) -> None:
        """Initialize default simulation scenarios."""
        
        # Scenario 1: Contract Negotiation
        s1 = SimulationScenario(
            "contract_negotiation",
            "Contract Negotiation: Securing Better Terms",
            "Learn how to negotiate a vendor contract to secure better pricing and terms"
        )
        s1.add_step(
            1,
            "Initial Vendor Proposal",
            """
            CloudServe Inc. has sent you an initial proposal for 12 months of cloud
            infrastructure services at $50,000/month with standard SLAs.
            
            Your company's historical average with other vendors is $45,000/month
            for comparable services.
            
            The contract requires a 2-year commitment.
            """,
            [
                "A) Accept the proposal as-is",
                "B) Request volume discount due to our scale",
                "C) Ask for competitive bids from 3 other vendors",
                "D) Propose 1-year term with performance-based increases",
            ],
            "Best choice: D - Propose flexible terms. This gives you an exit clause if they underperform."
        )
        s1.add_step(
            2,
            "SLA Negotiation",
            """
            The vendor refuses the 1-year term but offers:
            - $48,000/month (2% discount) for 2 years
            - 99.9% uptime SLA
            - 4-hour response time for P1 issues
            
            Your requirements are:
            - 99.95% uptime (you need high reliability)
            - 2-hour response for P1 (critical for your business)
            """,
            [
                "A) Accept - $2,000/month savings is good",
                "B) Counter with 99.95% uptime + price reduction",
                "C) Walk away - too expensive for what you need",
                "D) Accept SLA but add performance penalties for misses",
            ],
            "Best choice: D - Accept SLA but add penalties. Leverages their confidence in their uptime."
        )
        s1.add_step(
            3,
            "Final Decision",
            """
            After negotiation, you have two offers:
            
            Option 1: CloudServe
            - $48,000/month, 2-year commitment
            - 99.9% uptime, 4-hour response
            - 5% penalty for SLA violation
            
            Option 2: TechVendor (from RFP)
            - $50,000/month, 1-year commitment  
            - 99.95% uptime, 2-hour response
            - 10% penalty for SLA violation
            """,
            [
                "A) Choose CloudServe (cheaper)",
                "B) Choose TechVendor (better terms, flexibility)",
                "C) Request best-and-final from both",
                "D) Split services between both providers",
            ],
            "Best choice: C - Get final offers from both. You have negotiating leverage."
        )
        self.scenarios[s1.scenario_id] = s1
        
        # Scenario 2: SLA Violation Response
        s2 = SimulationScenario(
            "sla_violation",
            "SLA Violation: Managing a Critical Incident",
            "Navigate a critical SLA violation and mitigate business impact"
        )
        s2.add_step(
            1,
            "Incident Detected",
            """
            Your cloud infrastructure vendor (CloudServe) has experienced an outage.
            - Duration: 2.5 hours (still ongoing)
            - Severity: P1 - Core business systems offline
            - Estimated customers affected: 5,000
            - Expected SLA hit: 0.5% for the month
            
            Your SLA threshold is 99.95% - you're at 99.80%.
            
            The vendor promised 1-hour response. It's been 45 minutes.
            """,
            [
                "A) Wait for their resolution",
                "B) Escalate immediately to vendor executive",
                "C) Initiate fallback to backup vendor",
                "D) Activate business continuity plan",
            ],
            "Best choice: B+C - Escalate AND prepare fallback. Protect business first."
        )
        s2.add_step(
            2,
            "Vendor Communication",
            """
            Vendor calls: 'We're experiencing DDoS attack. ETA to resolution: 1 hour.'
            
            Your team estimates restoring from backup takes 30 minutes but
            may lose some recent transactions.
            
            Meanwhile, your CEO is asking for status.
            """,
            [
                "A) Trust vendor, wait for their resolution",
                "B) Start backup restoration immediately",
                "C) Both in parallel - force faster resolution",
                "D) Blame vendor publicly to manage expectations",
            ],
            "Best choice: C - Parallel approach minimizes downtime. Provides optionality."
        )
        s2.add_step(
            3,
            "Post-Incident Actions",
            """
            After 3 hours, services are restored. SLA violation confirmed: -0.75% for month.
            
            Vendor offers: 10% service credit on this month (~$4,800).
            
            Your actual costs from the outage:
            - Lost revenue: $80,000
            - Customer support: $15,000
            - Infrastructure repairs: $5,000
            """,
            [
                "A) Accept credit, move on",
                "B) Demand full compensation ($100k)",
                "C) Request $50k credit + contract renegotiation",
                "D) Terminate contract immediately",
            ],
            "Best choice: C - Negotiate both immediate relief AND contract changes."
        )
        self.scenarios[s2.scenario_id] = s2
        
        # Scenario 3: Budget Planning
        s3 = SimulationScenario(
            "budget_planning",
            "Budget Planning: Managing Variable Costs",
            "Plan for next fiscal year with multiple vendor contracts"
        )
        s3.add_step(
            1,
            "Current State",
            """
            You manage contracts with 5 vendors totaling $600,000 annual spend:
            
            1. CloudServe: $400k/year (infrastructure) - auto-renews in 60 days
            2. Analytics Vendor: $120k/year (expires in 45 days)
            3. Security: $50k/year (expires in 90 days)
            4. Consulting: $20k/year (monthly variable)
            5. Support: $10k/year (expires in 120 days)
            
            Budget request deadline: 30 days from now
            """,
            [
                "A) Budget based on current costs",
                "B) Plan 5% increase across all vendors",
                "C) Run competitive bidding before budgeting",
                "D) Consolidate vendors to reduce complexity",
            ],
            "Best choice: C - Bid before budgeting. You have time and leverage."
        )
        s3.add_step(
            2,
            "Vendor Renewal Strategy",
            """
            RFP results show:
            
            CloudServe (current): $400k/year
            Competitor A (new): $380k/year (-5%) but unproven
            Competitor B (new): $420k/year (+5%) but superior SLA
            
            Analytics:
            Current vendor: $120k/year (wants 15% increase)
            New vendor: $100k/year (new market entrant)
            
            CFO says: 'Save money where possible but don't sacrifice quality'
            """,
            [
                "A) Stay with all current vendors for stability",
                "B) Switch to cheapest option everywhere",
                "C) Mix - switch only where risk is lowest",
                "D) Negotiate hard with current vendors first",
            ],
            "Best choice: C - Strategic mix. Risk-based approach to spending."
        )
        s3.add_step(
            3,
            "Budget Finalization",
            """
            Your final negotiated numbers:
            - CloudServe: $400k (no change - firm on price)
            - Analytics: $110k (-8.3% vs current vendor)
            - Security: $50k (renew with same vendor)
            - Consulting: $25k (slight increase for headcount)
            - Support: $12k (inflation adjustment)
            
            Total: $597k (within budget!)
            """,
            [
                "A) Submit as-is",
                "B) Add 10% contingency buffer",
                "C) Push for more savings",
                "D) Distribute savings to other departments",
            ],
            "Best choice: B - Add contingency. You have room and it protects against overages."
        )
        self.scenarios[s3.scenario_id] = s3
    
    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Get a scenario by ID."""
        scenario = self.scenarios.get(scenario_id)
        return scenario.to_dict() if scenario else None
    
    def list_scenarios(self) -> List[Dict[str, Any]]:
        """List all available scenarios."""
        return [
            {
                "scenario_id": sid,
                "title": s.title,
                "description": s.description,
                "total_steps": len(s.steps),
            }
            for sid, s in self.scenarios.items()
        ]
    
    def get_scenario_step(self, scenario_id: str, step_num: int) -> Optional[Dict[str, Any]]:
        """Get a specific step from a scenario."""
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            return None
        
        for step in scenario.steps:
            if step["step"] == step_num:
                return step
        return None
    
    def evaluate_choice(
        self,
        scenario_id: str,
        step_num: int,
        choice_letter: str
    ) -> Dict[str, Any]:
        """Evaluate a user's choice and provide feedback."""
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            return {"error": "Scenario not found"}
        
        step = None
        for s in scenario.steps:
            if s["step"] == step_num:
                step = s
                break
        
        if not step:
            return {"error": "Step not found"}
        
        choice_index = ord(choice_letter.upper()) - ord("A")
        if choice_index < 0 or choice_index >= len(step["options"]):
            return {"error": "Invalid choice"}
        
        choice_text = step["options"][choice_index]
        
        # Simple evaluation based on expected outcome
        is_recommended = step["expected_outcome"].lower().startswith(f"best choice: {choice_letter.lower()}")
        
        feedback = "RECOMMENDED" if is_recommended else "ACCEPTABLE"
        
        return {
            "scenario_id": scenario_id,
            "step": step_num,
            "choice": f"{choice_letter.upper()}) {choice_text}",
            "feedback": feedback,
            "explanation": step["expected_outcome"],
            "next_step": step_num + 1 if step_num < len(scenario.steps) else None,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_simulator: Optional[InteractiveSimulator] = None


def get_simulator() -> InteractiveSimulator:
    """Get the global simulator instance."""
    global _simulator
    if _simulator is None:
        _simulator = InteractiveSimulator()
    return _simulator


if __name__ == "__main__":
    sim = get_simulator()
    
    print("=" * 80)
    print("PILOTH INTERACTIVE SIMULATIONS")
    print("=" * 80)
    print()
    
    # List scenarios
    print("Available Scenarios:")
    for scenario in sim.list_scenarios():
        print(f"  - {scenario['scenario_id']}: {scenario['title']}")
        print(f"    ({scenario['total_steps']} steps)")
    print()
    
    # Show first step of first scenario
    scen = sim.get_scenario("contract_negotiation")
    if scen:
        print(f"Scenario: {scen['title']}")
        print(f"Description: {scen['description']}")
        print()
        step1 = scen["steps"][0]
        print(f"Step 1: {step1['title']}")
        print(step1['situation'])
        for opt in step1['options']:
            print(f"  {opt}")
