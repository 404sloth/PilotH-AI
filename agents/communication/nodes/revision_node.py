"""
Revision Node for Communication Agent.

Extracts historical context and action items from previous meetings with
the same attendees or topic to brief the user before the next meeting.
"""

from typing import Dict, Any, List
from agents.communication.schemas import MeetingState
from agents.communication.tools.meeting_search_tool import MeetingSearchTool, MeetingSearchInput

def revision_node(state: MeetingState) -> MeetingState:
    """
    Search for past related meetings, extract action items and summaries,
    and append a 'historical context' view to the state for the brief context.
    """
    params = state.get("params", {})
    topic = params.get("topic")
    attendee = params.get("attendee_email")
    
    if not topic and not attendee:
        # No specific topic or attendee to revise against
        return state
        
    tool = MeetingSearchTool()
    
    # We want transcripts for revision
    res = tool.execute(MeetingSearchInput(
        title=topic, 
        attendee_email=attendee, 
        limit=3, 
        include_transcript=True
    ))
    
    if not res.found or len(res.meetings) == 0:
        state["data"]["historical_context"] = "No past meetings found to revise."
        return state
        
    context_lines = []
    context_lines.append(f"Found {res.count} recent related meetings.")
    
    all_action_items = []
    for m in res.meetings:
        context_lines.append(f"- **{m.title}** ({m.start_time or 'Past'}):")
        if m.transcript_summary:
            context_lines.append(f"  *Transcript Summary*: {m.transcript_summary}")
        if m.action_items:
            all_action_items.extend(m.action_items)
            
    if all_action_items:
        context_lines.append("\n**Open Action Items / Promises from previous meetings:**")
        for item in set(all_action_items):
            context_lines.append(f"- [ ] {item}")
            
    state["data"]["historical_context"] = "\n".join(context_lines)
    return state
