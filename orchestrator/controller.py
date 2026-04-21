"""
Orchestrator Controller — main entry point for all user requests.
Parses intent → decomposes tasks → routes to agents → aggregates results.
"""

from __future__ import annotations

import logging
import uuid
import json
from typing import Any, Dict, Optional, List
import os
import re
from langchain_core.runnables import RunnableConfig

from config.settings import Settings
from memory.session_store import get_session_store
from memory.global_context import get_global_context
from llm.token_counter import get_token_counter
from llm.model_factory import ConversationManager, Conversation
from orchestrator.schemas import OrchestratorResponse

logger = logging.getLogger(__name__)


class OrchestratorController:
    """
    Central router and coordinator.

    Workflow:
      1. Parse intent from user message (IntentParser)
      2. Decompose into subtasks (TaskDecomposer)
      3. Route each subtask to the appropriate agent (AgentRouter)
      4. Aggregate results and save to memory
    """

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.session_store = get_session_store()
        self.global_ctx = get_global_context()
        self.token_counter = get_token_counter()

    async def handle(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        agent_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message and return a formatted blocking response.
        Compatible with standard POST /run routes.
        """
        from graphs.orchestration_graph import build_orchestration_graph, OrchestrationState
        from observability.pii_sanitizer import PIISanitizer
        
        session_id = session_id or str(uuid.uuid4())
        runtime_context = dict(context or {})
        
        # 1. Initialize Graph & State
        graph = build_orchestration_graph()
        initial_state: OrchestrationState = {
            "session_id": session_id,
            "user_message": message,
            "context": PIISanitizer.sanitize_dict(runtime_context),
            "messages": [],
            "agent_results": {},
            "task_index": 0,
            "trace": []
        }

        config = RunnableConfig(
            callbacks=[], 
            tags=["orchestrator", "blocking", session_id],
            metadata={"session_id": session_id},
            recursion_limit=50
        )

        # 2. Run graph to completion
        final_state = await graph.ainvoke(initial_state, config=config)
        
        # 3. Format Output
        intent = final_state.get("intent", {})
        formatted_result = self._format_final_output_with_llm(
            final_state.get("agent_results", {}), 
            intent, 
            message, 
            config=config
        )

        return {
            "response": formatted_result.get("response", ""),
            "data": formatted_result.get("data", {}),
            "suggestions": formatted_result.get("suggestions", []),
            "conversation_id": session_id,
            "session_id": session_id,
            "metadata": {
                "agent": intent.get("agent", "unknown"),
                "action": intent.get("action", "unknown"),
                "intent_reasoning": intent.get("reasoning", ""),
                "final_response": final_state.get("final_response")
            }
        }

    async def handle_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        agent_hint: Optional[str] = None,
    ):
        """
        Process a user message using astream_events to provide real-time updates.
        Yields:
            TraceEvent | OrchestratorResponse
        """
        from observability.logger import get_logger
        from observability.pii_sanitizer import PIISanitizer
        from graphs.orchestration_graph import build_orchestration_graph, OrchestrationState
        from orchestrator.schemas import TraceEvent, OrchestratorResponse
        import uuid

        session_id = session_id or str(uuid.uuid4())
        runtime_context = dict(context or {})
        
        # 1. Initialize Graph & State
        graph = build_orchestration_graph()
        initial_state: OrchestrationState = {
            "session_id": session_id,
            "user_message": message,
            "context": PIISanitizer.sanitize_dict(runtime_context),
            "messages": [],
            "agent_results": {},
            "task_index": 0,
            "trace": []
        }

        # 🔍 LangSmith Configuration
        config = RunnableConfig(
            callbacks=[], 
            tags=["orchestrator", session_id],
            metadata={"session_id": session_id},
            recursion_limit=50
        )

        # 2. Iterate over the event stream
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            kind = event["event"]
            name = event["name"]
            
            # Map LangGraph events to TraceEvents
            if kind == "on_node_start":
                # Filter out system nodes if too noisy
                if name in ("START", "END", "__start__", "__end__"): continue
                
                yield TraceEvent(
                    type="agent" if "agent" in name.lower() else "status",
                    name=name.replace("_", " ").title(),
                    status="running",
                    details=f"Executing {name}..."
                )
            
            elif kind == "on_tool_start":
                yield TraceEvent(
                    type="tool",
                    name=name.replace("_", " ").title(),
                    status="running",
                    details=f"Calling tool: {name}"
                )
            
            elif kind == "on_tool_end":
                yield TraceEvent(
                    type="tool",
                    name=name.replace("_", " ").title(),
                    status="completed",
                    details=f"Tool {name} finished."
                )

            elif kind == "on_node_end":
                if name in ("START", "END", "__start__", "__end__"): continue
                yield TraceEvent(
                    type="agent" if "agent" in name.lower() else "status",
                    name=name.replace("_", " ").title(),
                    status="completed"
                )

        # 3. Final Result Gathering
        # Run one final invoke to get the completed state (or use values from stream if preferred)
        # Note: astream_events yields values as well, but for simplicity here we re-invoke or take last
        final_state = await graph.ainvoke(initial_state, config=config)
        
        # 4. Format Output (Re-using logic from original handle)
        intent = final_state.get("intent", {})
        formatted_result = self._format_final_output_with_llm(
            final_state.get("agent_results", {}), 
            intent, 
            message, 
            config=config
        )

        yield OrchestratorResponse(
            response=formatted_result.get("response", ""),
            agent=intent.get("agent", "unknown"),
            action=intent.get("action", "unknown"),
            thought=final_state.get("final_response"), # Use compiled response or thoughts
            intent_reasoning=intent.get("reasoning", ""),
            data=formatted_result.get("data", {}),
            suggestions=formatted_result.get("suggestions", []),
            trace=[] # Final state could include full trace here
        )

    def _summarize_history(self, older_messages: List[Dict[str, Any]], existing_summary: Optional[str] = None, config: Optional[RunnableConfig] = None) -> str:
        """Create a compact summary of older conversation history."""
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage
        
        if not older_messages:
            return existing_summary or ""
            
        history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in older_messages])
        prompt = f"""Summarize the following conversation history into a single, highly compact paragraph. 
Focus on key decisions, entities mentioned (vendors, project IDs), and active tasks.
Keep it under 150 words.

Existing Summary (to be merged): {existing_summary or "None"}
New History:
{history_str}
"""
        try:
            llm = get_llm(temperature=0.2)
            resp = llm.invoke([HumanMessage(content=prompt)], config=config)
            return resp.content.strip()
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return existing_summary or "Conversation in progress."

    def _generate_dynamic_help(self, user_query: str, registry: Dict[str, Any]) -> str:
        """Use LLM to generate a professional help message based on current registry."""
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        # Simplify registry for LLM context
        capabilities = []
        for agent_id, info in registry.items():
            if agent_id == "system": continue
            agent_cap = {
                "name": info.get("agent_name"),
                "description": info.get("agent_description"),
                "features": [act["description"] for act in info.get("actions", {}).values()]
            }
            capabilities.append(agent_cap)

        prompt = f"""You are PilotH, an Enterprise Intelligence Console. 
The user is asking about your features or saying hello.
Based on the registered capabilities below, write a professional, welcoming response.

Capabilities:
{json.dumps(capabilities, indent=2)}

User Query: "{user_query}"

Guidelines:
- Be concise but thorough.
- Group features by domain (Vendor Management, Communications, etc.).
- Use bullet points for readability.
- Mention that you can handle complex data requests and formatting.
"""
        try:
            llm = get_llm(temperature=0.3)
            resp = llm.invoke([HumanMessage(content=prompt)])
            return resp.content.strip()
        except Exception:
            return "I am PilotH. I can help with Vendor Management, Meeting Communication, and Knowledge Retrieval. How can I assist?"

    def _format_final_output_with_llm(self, result: Dict[str, Any], intent: Dict[str, Any], original_query: str, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """Use LLM to intelligently format the raw agent data into a professional enterprise layout."""
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        agent = intent.get("agent", "")
        action = intent.get("action", "")
        
        # CLEAN PAYLOAD: Ignore internal state fields like 'messages', 'logic', etc.
        # This keeps the formatting LLM focused on the actual data.
        internal_keys = {"messages", "logic", "reflection", "requires_human_review", "checkpoint", "reflection_log"}
        clean_result = {k: v for k, v in result.items() if k not in internal_keys and v not in (None, [], {})}
        
        # Safely convert to string
        def safe_serialize(obj):
            try:
                import json
                return json.dumps(obj, indent=2, default=str)
            except Exception:
                return str(obj)
                
        raw_payload = safe_serialize(clean_result)[:2000] # Reduced to 2000 for token efficiency
        if len(safe_serialize(clean_result)) > 2000:
            raw_payload += "\n... [TRUNCATED]"

        prompt = f"""You are a content formatter for PilotH.
USER REQUEST: "{original_query}"
INTELLIGENCE: {agent} / {action}
DATA:
{raw_payload}

INSTRUCTIONS:
1. STRUCTURE: Use clear, hierarchical headings (##) and sub-headings (###). **DO NOT use '=====' or '-------' lines.**
2. TABLES: If the data contains lists of items (vendors, meetings, metrics, persons), ALWAYS present them in a clean, high-density Markdown Table format.
   - Extract at least 4-5 relevant columns for each row.
3. BULLETS: Use bullet points for key findings or risks. 
4. TYPOGRAPHY: Use **bold** for names and `code` for IDs.
5. EXECUTIVE SUMMARY: Start with a 1-2 sentence high-level summary.
6. SUGGESTIONS: Provide exactly 3 short follow-up suggestions.
   - Format: [SUGGESTIONS] ["S1", "S2", "S3"] [/SUGGESTIONS] (Always at the absolute bottom).
7. DATA INTEGRITY: Never show 'null' or 'None'. Use 'N/A' or 'Requested' for missing metrics.
8. BRANDING: Refer to yourself as 'Human CoPilot' if needed.
9. NO DECORATIONS: DO NOT use '====' or '----' or '____' lines as separators. Use sub-headings instead.
"""

        try:
            llm = get_llm(temperature=0.1)
            resp = llm.invoke([HumanMessage(content=prompt)], config=config)
            
            content = resp.content.strip()
            
            # Post-process to remove unwanted lines/artifacts
            lines = content.split("\n")
            cleaned_lines = []
            for line in lines:
                # Remove common separators generated by LLMs
                if re.match(r"^[-=_*]{3,}$", line.strip()):
                    continue
                cleaned_lines.append(line)
            content = "\n".join(cleaned_lines).strip()

            suggestions = []
            
            # Extract suggestions from the special block
            match = re.search(r"\[SUGGESTIONS\](.*?)(?:\[/SUGGESTIONS\]|$)", content, re.DOTALL)
            if match:
                try:
                    # Clean the JSON string before loading
                    clean_json = match.group(1).strip()
                    if clean_json.startswith("```json"): clean_json = clean_json[7:-3].strip()
                    elif clean_json.startswith("```"): clean_json = clean_json[3:-3].strip()
                    
                    suggestions = json.loads(clean_json)
                    content = content[:match.start()].strip() + "\n" + content[match.end():].strip()
                    content = content.replace("[/SUGGESTIONS]", "").strip()
                except Exception: 
                    # Fallback match if JSON load fails
                    inner = match.group(1).replace('"', '').replace('[', '').replace(']', '').split(',')
                    suggestions = [s.strip() for s in inner if s.strip()]
                    content = content.replace(match.group(0), "").strip()
                    content = content.replace("[/SUGGESTIONS]", "").strip()
                
            return {"response": content, "data": result, "suggestions": suggestions}
        except Exception as e:
            logger.warning(f"Formatting LLM failed: {e}. Falling back to manual formatting.")
            return self._manual_fallback_formatter(result, intent, original_query)

    def _manual_fallback_formatter(self, result: Dict[str, Any], intent: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Simple rule-based formatter to ensure user gets a table even if LLM fails."""
        lines = [f"## Results for: {query.capitalize()}", ""]
        
        # Identify the primary data list
        data_list = []
        headers = []
        
        if "vendors" in result and isinstance(result["vendors"], list) and result["vendors"]:
            data_list = result["vendors"]
            headers = ["Vendor ID", "Name", "Tier", "Country", "Status"]
        elif "ranked_vendors" in result and isinstance(result["ranked_vendors"], list) and result["ranked_vendors"]:
            data_list = result["ranked_vendors"]
            headers = ["Name", "Tier", "Fit Score", "Country"]
        elif "meetings" in result and isinstance(result["meetings"], list) and result["meetings"]:
            data_list = result["meetings"]
            headers = ["Title", "Time", "Participants"]

        if data_list:
            # Build Table
            header_row = "| " + " | ".join(headers) + " |"
            sep_row = "| " + " | ".join(["---"] * len(headers)) + " |"
            lines.append(header_row)
            lines.append(sep_row)
            
            for item in data_list[:20]: # Limit to 20 for readability
                row = []
                for h in headers:
                    key = h.lower().replace(" ", "_")
                    if key == "status": key = "contract_status"
                    val = item.get(key, item.get(h.lower(), "N/A"))
                    row.append(str(val))
                lines.append("| " + " | ".join(row) + " |")
            
            lines.append("\n### Executive Analysis (Auto-Generated)")
            lines.append(f"Successfully retrieved {len(data_list)} record(s) matching your request. Displaying the top matches in tabular form.")
        else:
            lines.append("Search executed successfully, but no matching records were found in the database. Please try adjusting your filters (e.g. check country codes or service names).")

        return {"response": "\n".join(lines), "data": result}
