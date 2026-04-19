# Strategic Enhancements: Vendor Management & Communication Agents

This document outlines the proposed architectural improvements and functional upgrades for the PilotH platform, specifically focusing on Vendor Management, Communication workflows, and Core Orchestration.

---

## 1. SLA Compliance Evaluation (Refinement)

**Current State:** Basic metric fetching (target vs actual) and general compliance rate calculation.
**Requirement:** Detailed breakdown (uptime, response time, resolution time), mapping to SLA clauses, and audit trails.

### Proposed Changes:
- **Enhanced `SLAMonitorTool`**:
  - Update schema to support granular metrics: `uptime_percentage`, `p99_latency`, `avg_resolution_time`, `first_response_time`.
  - Integration with `IncidentLogs` to count severity-based violations.
- **New `SLABreachAnalyzer` Node**:
  - Implementation of a logic layer that maps fetched metrics to specific contract clauses (retrieved via `ContractParserTool`).
  - Calculation of "Compliance Score" based on weighted importance of different metrics.
- **Audit Trail Generator**:
  - Automatic generation of a `ComplianceEvidence` object containing raw data points, the rule applied, and the resulting score, ensuring explainability.

---

## 2. Vendor Recommendation Agent (Refinement)

**Current State:** Ranks vendors by fit score using historical performance.
**Requirement:** Tabular comparison with specific dimensions (Cost, SLA Score, Latency, Reliability, Fit Score) and detailed justification.

### Proposed Changes:
- **Tabular Comparison Engine**:
  - Modify `VendorMatcherTool` to output a structured `ComparisonMatrix`.
  - Dimensions to include:
    - **Cost**: Monthly rate + cost competitiveness.
    - **SLA Score**: Historical compliance average.
    - **Latency/Speed**: Performance metrics from technical logs.
    - **Reliability**: On-time delivery rate + incident frequency.
    - **Fit Score**: Composite score tailored to specific project requirements.
- **Justification Engine (LLM-driven)**:
  - A dedicated node that uses the `ComparisonMatrix` to write "Pros/Cons" and "Reason for Selection/Rejection" for each candidate.
  - Multi-criteria decision logic: Users can weight dimensions (e.g., "Prioritize Latency over Cost").

---

## 3. Communication Agent: Intelligent Meeting Retrieval & Context

**Requirement:** Ability to fetch meeting transcripts by date, time, title, or attendees. "Revise" important points from previous meetings before a new one on the same topic/with same people.

### Proposed Changes:
- **Enhanced `MeetingSearchTool`**:
  - New tool dedicated to searching `meeting_db` using flexible filters:
    - `date_range`: Find meetings within a specific period.
    - `attendee_ids/emails`: Find all meetings where Person X was present.
    - `title_pattern`: Semantic search on meeting titles.
- **Cross-Meeting "Revision" Node**:
  - A new workflow step in the `CommunicationAgent` that triggers before "Briefing" or "Scheduling".
  - It searches for the last 3-5 related meetings (same attendees or overlapping topics).
  - Uses `MeetingSummarizerTool` to pull key decisions and "open action items" from those past meetings.
- **Important Points Synthesis**:
  - Generates a "Historical Context" block for the user: *"In your last meeting on this topic (March 15), you decided X, but action item Y is still pending. Should we address this today?"*

---

## 4. Gap Detection & Action Agent (New)

**Objective**: Identify unmet requirements and trigger corrective actions.

### Proposed Architecture:
- **`CapabilityMapper` Tool**:
  - Maps existing vendor offerings to a standardized "Service Capability Taxonomy".
- **`RequirementAnalyzer` Node**:
  - Parses client project needs into the same taxonomy.
- **`GapDetector` Node**:
  - Compares *Required* vs *Available*.
  - Outputs a **Gap Report**:
    - **Requirement**: "Real-time stream processing"
    - **Status**: "Missing"
    - **Impact**: "Critical - prevents project launch"
- **Action Recommender**:
  - Logic to suggest: "Onboard New Vendor", "Upgrade Existing Vendor", or "Redistribute Load".

---

## 5. Robust Intent Detection & PII Safety

**Requirement**: Robust intent detection without exposing PII to LLMs. Apply masking at the entry point.

### Proposed Changes:
- **Sanitized Intent Parsing**:
  - Update `IntentParser` to strictly use `PIISanitizer` *before* the prompt is constructed.
  - **Double-Pass Parsing**: 
    1. Pass 1: Masked query to detect Agent/Action (e.g., "Schedule meeting with [USER_1] at [TIME]").
    2. Pass 2: Local rule-based extraction or specific parameter extraction (if needed) to map [USER_1] back to the real email using `meeting_db`.
- **Enhanced PII Masking**:
  - Update `PIISanitizer` to handle Project Names, Vendor Names (optionally), and sensitive internal IDs using a temporary session-based mapping.
- **Prompt Hardening**:
  - Use "Few-Shot" examples in `AdvancedIntentParser` that specifically demonstrate how to handle ambiguous communication requests (e.g., "the meeting yesterday" vs "the meeting on Friday").

---

## 6. Minimal & Effective Human-in-the-Loop (HITL)

**Requirement:** Proper HITL implementation that is minimal but triggers when truly needed.

### Proposed Triggers:
- **High-Risk Thresholds**:
  - **Financial**: Any vendor selection involving budgets > $10,000/month.
  - **External Communication**: Sending automated emails to external vendor domains (detected via `has_external` flag in `CalendarCreateOutput`).
  - **SLA Escalation**: Any breach notification that labels a vendor as "Non-Compliant".
- **Refined Approval UI**:
  - Use `HITLManager` to pause the graph and present the user with a "Conflict Resolution" or "Approval" card containing the **RationaleContext** (Why this is happening).

---

## 7. Advanced Prompt Engineering & Tool Robustness

**Objective**: Improve the reliability of tool calls and reduce LLM hallucinations in reasoning tasks.

### Proposed Changes:
- **Strict Schema Enforcement**:
  - Update all tool `args_schema` with explicit Pydantic `Field` descriptions that include example values and "Negative Constraints" (e.g., "Do not use this tool if the vendor_id is unknown").
- **Chain-of-Thought (CoT) Prompting**:
  - Implement CoT in complex reasoning nodes like `SLABreachAnalyzer` and `GapDetector`.
  - Prompts will require the LLM to first list the evidence, then the applicable rule, and finally the decision.
- **Hallucination Guardrails**:
  - Add a "Verification Node" that cross-references LLM-generated summaries against raw tool outputs before finalizing the agent response.

---

## 8. Graph-State Aware Intent Detection

**Objective**: Make intent detection smarter by considering the current state of the conversation and the execution graph.

### Proposed Changes:
- **State-Injected Parsing**:
  - Pass the current `GraphState` (e.g., "currently evaluating Vendor X") to the `IntentParser`.
  - This allows for shorter, relative user prompts like "What about their SLA?" to be correctly mapped to `monitor_sla(vendor_id='Vendor X')`.
- **Dynamic Few-Shot Loading**:
  - Load different sets of few-shot examples into the `AdvancedIntentParser` based on the active agent, improving accuracy for specialized domains.

---

## 9. Architectural Robustness & Future-Proofing

### A. Unified Vendor Knowledge Graph
- Move from flat SQLite tables to a graph-based representation where nodes are Vendors, Contracts, and Capabilities.

### B. Explainable Decision Infrastructure
- Every decision made by the Vendor Agent should include a `RationaleContext` object.
- This object stores: `[Metrics Used] + [Contract Clauses Reference] + [LLM Reasoning Step]`.

### C. Continuous Performance Learning
- The `PerformanceAggregator` should run as a background task, periodically updating `VendorPerformanceProfile`.

---

## 10. Coding Agent Guidelines (LLM-Specific Instructions)

**Objective**: Ensure LLM coders produce robust, project-aligned code without regressions.

### A. The "Do No Harm" Protocol
- **Research First**: Before any edit, use `grep_search` to find all references to the symbol being modified.
- **Surgical Edits**: Prefer the `replace` tool over `write_file` for large files to avoid overwriting unrelated logic.
- **Verify Dependencies**: If changing a schema in `schemas/`, immediately search for all agents and tools that import it.

### B. Project-Specific Standards
- **Strict Typing**: All new functions must have Python type hints and Pydantic models for I/O.
- **Error Handling**: Never use bare `except:`. Always log errors using `observability.logger`.
- **Tool Logic**: Logic must reside in the tool's `execute` method or a dedicated logic class, never in the orchestrator.

### C. Implementation Prompt Template
> "Implement [FEATURE] in [FILE]. 
> 1. Identify existing patterns for [FEATURE TYPE]. 
> 2. Create/Update necessary Pydantic schemas in `schemas/`.
> 3. Implement tool logic ensuring PII masking is applied to outputs.
> 4. Add unit tests in `tests/` reproducing the success case.
> 5. Run `ruff check` and `pytest` before finality."

---

## 11. Frontend Professionalism & Trust-Building (Updated)

**Objective**: Create a "High-Trust" UI that feels like a professional enterprise tool.

### A. Design System Upgrades (Implemented)
- **Floating Glassmorphism**: Replaced hard borders with subtle shadows (`box-shadow: 0 4px 16px rgba(0,0,0,0.04)`) and rounded corners (`borderRadius: 24`).
- **Clean Message Rendering**: 
  - User messages are right-aligned with a distinct primary blue bubble.
  - Agent messages are left-aligned with a clean white background and an icon-based identifier to differentiate between Vendor, Communication, and Knowledge agents.
- **Enterprise Palette**: Standardized on professional Google-style colors (`#1a73e8` for Primary, `#f8f9fa` for Backgrounds, `#202124` for Text).

### B. Layout Improvements (Implemented)
- **Side-by-Side Context**: The main chat view now features a 70/30 split. The left column handles the conversation, while the right column provides "Thread details" and "Live Routing" metadata.
- **Minimalist Sidebar**: Navigation and "Recent Chats" are now housed in a clean white sidebar with hover-active states and clear section labels.
- **Action-Oriented Dashboard**: The dashboard now uses a clean grid for Strategic Alerts, System Health, and Quick Action cards.

### C. Visual Trust & Transparency (Implemented)
- **Live Routing Overlays**: Each agent message now includes an expandable "Routing" block showing exactly which agent/action was triggered and which tools were available.
- **Thinking States**: A clean "Thinking..." badge with a spinner appears in the header during LLM processing, providing immediate feedback to the user.

### D. Next Steps for UX
- **Modularization**: Break the monolithic `App.tsx` into specialized components in `src/components/` for easier maintenance.
- **Advanced Task Views**: Implement full-width professional grids for Vendor Comparison and Timeline views for Contract Lifecycle.

---

## Implementation Priority (Frontend & Coding)
1. **Priority 1**: (DONE) UI/UX Overhaul for Premium Aesthetic.
2. **Priority 2**: Modularize `App.tsx` into `components/`.
3. **Priority 3**: Implement "Comparison Matrix" grid for Vendor recommendations.
4. **Priority 4**: Establish the "Coding Agent Guide" as a mandatory system instruction.
