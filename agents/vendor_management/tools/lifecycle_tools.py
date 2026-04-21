import json
import logging
import uuid
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from llm.model_factory import get_llm
from integrations.data_warehouse.vendor_db import (
    get_meeting_full,
    save_rfp,
    get_rfp,
    get_all_active_vendors,
    save_vendor_response,
    get_vendor_responses,
    update_vendor_response_score,
    select_vendor_for_project
)

logger = logging.getLogger(__name__)

# --- RFP Generation Tool ---

@tool
def generate_rfp_from_meeting(meeting_id: str) -> str:
    """
    Strategically converts a negotiation or business requirement meeting transcript into a formal RFP document.
    
    Args:
        meeting_id (str): The unique ID of the meeting containing the transcript.
        
    Usage: Use this when the user wants to initiate a vendor sourcing process based on internal requirements meetings.
    Returns: A confirmation message including the generated RFP-ID.
    """
    try:
        meeting = get_meeting_full(meeting_id)
        if not meeting:
            return f"Error: Meeting '{meeting_id}' not found."
        
        transcript = meeting.get("transcript")
        if not transcript:
            return f"Error: No transcript found for meeting '{meeting_id}'."
        
        project_id = meeting.get("project_id")
        if not project_id:
            return f"Error: Meeting '{meeting_id}' is not linked to any project."

        # Fetch local Ollama LLM
        llm = get_llm("ollama")
        
        prompt = f"""You are a Strategic Procurement Specialist. 
Convert the following business meeting transcript into a structured RFP (Request for Proposal).

TRANSCRIPT:
\"\"\"{transcript}\"\"\"

The structured RFP MUST include:
1. Executive Summary/Background
2. Project Scope
3. Technical & Functional Requirements
4. Proposed Timeline
5. Evaluation Criteria

Produce a professional, detailed document."""

        response = llm.invoke(prompt)
        rfp_content = response.content
        
        rfp_id = f"RFP-{uuid.uuid4().hex[:6].upper()}"
        save_rfp(rfp_id, project_id, rfp_content)
        
        return f"✅ SUCCESS: RFP '{rfp_id}' generated and stored for project '{project_id}'."

    except Exception as e:
        logger.error(f"Error in generate_rfp_from_meeting: {e}")
        return f"Error: {str(e)}"


# --- Vendor Response Generation Tool ---

@tool
def generate_mock_vendor_responses(rfp_id: str) -> str:
    """
    Orchestrates the generation of professional competitive bids from active vendors in response to a specific RFP.
    
    Args:
        rfp_id (str): The ID of the RFP to respond to.
        
    Usage: Use this to simulate market responses or to accelerate the procurement lifecycle during drafting.
    Returns: A summary of responses generated and vendors engaged.
    """
    try:
        rfp = get_rfp(rfp_id)
        if not rfp:
            return f"Error: RFP '{rfp_id}' not found."
        
        rfp_content = rfp["content"]
        vendors = get_all_active_vendors()
        
        if not vendors:
            return "Error: No active vendors found to respond."

        llm = get_llm("ollama")
        response_ids = []
        
        for vendor in vendors:
            vendor_name = vendor["name"]
            # Note: expertise is mocked here as part of vendor name or can be fetched if exists
            
            prompt = f"""You are the Bid Manager for {vendor_name}. 
Your company is responding to the following RFP.

RFP CONTENT:
\"\"\"{rfp_content[:2000]}\"\"\"

Task: Write a professional RFP response.
Include:
1. Vendor Qualifications & Experience
2. Proposed Solution Overview
3. Mock Pricing Estimate (USD)
4. Implementation Timeline

Maintain a tone consistent with {vendor_name}'s profile."""

            response = llm.invoke(prompt)
            resp_id = f"RESP-{uuid.uuid4().hex[:6].upper()}"
            save_vendor_response(resp_id, rfp_id, vendor["id"], response.content)
            response_ids.append(resp_id)

        return f"✅ SUCCESS: Generated {len(response_ids)} mock responses for RFP '{rfp_id}'."

    except Exception as e:
        logger.error(f"Error in generate_mock_vendor_responses: {e}")
        return f"Error: {str(e)}"


# --- Vendor Response Evaluation Tool ---

@tool
def evaluate_vendor_responses(rfp_id: str) -> str:
    """
    Perform a comparative analysis and scoring of all vendor responses received for a specific RFP.
    
    Args:
        rfp_id (str): The ID of the RFP whose responses need evaluation.
        
    Usage: Critical for vendor selection. Use this once responses are in to rank vendors by technical and financial fit.
    Returns: A ranked list of vendors with technical scores and analysis.
    """
    try:
        rfp = get_rfp(rfp_id)
        if not rfp:
            return f"Error: RFP '{rfp_id}' not found."
        
        responses = get_vendor_responses(rfp_id)
        if not responses:
            return f"Error: No responses found for RFP '{rfp_id}'."

        llm = get_llm("ollama")
        
        all_evaluations = []
        
        for resp in responses:
            vendor_name = resp["vendor_name"]
            resp_text = resp["response_text"]
            
            prompt = f"""You are a neutral Technical Auditor.
Evaluate this vendor response against the original RFP requirements.

RFP SUMMARY:
\"\"\"{rfp["content"][:1000]}\"\"\"

VENDOR RESPONSE ({vendor_name}):
\"\"\"{resp_text[:2000]}\"\"\"

Task: Provide a score (0-100) and a brief justification.
Output format MUST be valid JSON:
{{
  "vendor_name": "{vendor_name}",
  "score": 85,
  "justification": "Detailed reasoning here..."
}}"""

            llm_response = llm.invoke(prompt)
            try:
                # Basic JSON extraction (in case LLM adds markdown)
                json_str = llm_response.content.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                
                eval_data = json.loads(json_str)
                score = float(eval_data.get("score", 0))
                update_vendor_response_score(resp["id"], score)
                all_evaluations.append(eval_data)
            except Exception as json_err:
                logger.warning(f"Failed to parse JSON for {vendor_name}: {json_err}")
                all_evaluations.append({
                    "vendor_name": vendor_name,
                    "score": 0,
                    "justification": f"Failed to parse LLM evaluation: {str(json_err)}"
                })

        # Rank results
        all_evaluations.sort(key=lambda x: x["score"], reverse=True)
        
        result_text = f"Ranked Evaluations for RFP {rfp_id}:\n"
        for i, ev in enumerate(all_evaluations, 1):
            result_text += f"{i}. {ev['vendor_name']}: {ev['score']}/100 - {ev['justification'][:150]}...\n"
            
        return result_text

    except Exception as e:
        logger.error(f"Error in evaluate_vendor_responses: {e}")
        return f"Error: {str(e)}"


# --- Vendor Selection Helper Tool ---

@tool
def select_vendor_helper(project_id: str, vendor_id: str) -> str:
    """
    Execution tool to officially select and lock a vendor for a specific project.
    
    Args:
        project_id (str): The ID of the project.
        vendor_id (str): The ID of the vendor to select.
        
    Usage: Use this as the final step of a selection process after evaluations are complete.
    Returns: Success confirmation.
    """
    try:
        select_vendor_for_project(project_id, vendor_id)
        return f"✅ SUCCESS: Vendor '{vendor_id}' has been selected for Project '{project_id}'."
    except Exception as e:
        return f"Error updating selection: {str(e)}"


# --- SOW & Milestone Extraction Tool ---

@tool
def generate_sow_from_meeting(meeting_id: str) -> str:
    """
    Creates a Statement of Work and extracts milestones from a negotiation meeting.
    Input: meeting_id
    Returns: SOW ID and count of milestones created.
    """
    from datetime import datetime, timedelta
    try:
        meeting = get_meeting_full(meeting_id)
        if not meeting: return f"Error: Meeting '{meeting_id}' not found."
        
        project_id = meeting.get("project_id")
        # In a real scenario, we'd fetch the selected_vendor_id from the project
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT vendor_id FROM projects WHERE id = ?", (project_id,))
            row = cur.fetchone()
            vendor_id = row[0] if row else None
            
        if not vendor_id: return "Error: No vendor selected for this project yet."

        llm = get_llm("ollama")
        prompt = f"""Extract SOW details from this negotiation transcript.
TRANSCRIPT: \"\"\"{meeting.get("transcript")}\"\"\"

Output valid JSON ONLY with keys:
- project_name: string
- milestones: list of {{ "title": string, "days_offset": int }}
- acceptance_criteria: string
- payment_terms: string
"""
        response = llm.invoke(prompt)
        # JSON cleaning
        content = response.content.strip()
        if "```json" in content: content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content: content = content.split("```")[1].split("```")[0].strip()
        
        data = json.loads(content)
        sow_id = f"SOW-{uuid.uuid4().hex[:6].upper()}"
        
        sow_text = f"SOW for {data['project_name']}\n\nCriteria: {data['acceptance_criteria']}\nTerms: {data['payment_terms']}"
        save_sow(sow_id, project_id, vendor_id, sow_text)
        
        start_date = datetime.now()
        for m in data.get("milestones", []):
            m_id = f"MS-{uuid.uuid4().hex[:6].upper()}"
            due_date = (start_date + timedelta(days=m["days_offset"])).strftime("%Y-%m-%d")
            save_lifecycle_milestone(m_id, sow_id, m["title"], due_date)
            
        return f"✅ SUCCESS: SOW '{sow_id}' created with {len(data.get('milestones', []))} milestones for Project '{project_id}'."
    except Exception as e:
        logger.error(f"SOW Generation failed: {e}")
        return f"Error: {str(e)}"


# --- Daily Status Simulation Tool ---

@tool
def simulate_daily_status(project_id: str) -> str:
    """
    Simulates tactical daily tasks and progress for all milestones in a project.
    Input: project_id
    Returns: Summary of tasks generated and statuses updated.
    """
    import random
    from datetime import datetime, timedelta
    try:
        milestones = get_milestones_for_project(project_id)
        if not milestones: return "Error: No milestones found to simulate."

        llm = get_llm("ollama")
        total_tasks = 0
        
        for m in milestones:
            prompt = f"Suggest 4 short tactical tasks to achieve milestone: '{m['title']}'. Return as comma-separated list."
            resp = llm.invoke(prompt)
            tasks = [t.strip() for t in resp.content.split(",")][:5]
            
            m_worst_status = "on-time"
            for i, task_desc in enumerate(tasks):
                total_tasks += 1
                planned_date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
                
                # Simulation Logic
                roll = random.random()
                if roll < 0.70: # 70% Completed on-time
                    status, act_date = "completed", planned_date
                elif roll < 0.90: # 20% Delayed
                    status, act_date = "completed", (datetime.now() + timedelta(days=i+2)).strftime("%Y-%m-%d")
                    if m_worst_status == "on-time": m_worst_status = "delayed"
                else: # 10% Blocked
                    status, act_date = "blocked", None
                    m_worst_status = "delayed" # milestone is delayed if anything is blocked

                save_daily_status(m["id"], task_desc, planned_date, act_date, status)
            
            # If all tasks are completed, milestone might be completed
            # Simplified: update milestone based on worst status found
            update_milestone_status(m["id"], m_worst_status)

        return f"✅ SUCCESS: Simulated {total_tasks} daily tasks across {len(milestones)} milestones for project '{project_id}'."
    except Exception as e:
        return f"Error in simulation: {str(e)}"


# --- Project Health Computation Tool ---

@tool
def compute_project_health(project_id: str) -> str:
    """
    Calculates the overall health of a project based on milestone and task status.
    Input: project_id
    Returns: Health color, progress %, and a risk report.
    """
    try:
        metrics = get_project_health_metrics(project_id)
        m_stats = metrics["milestones"]
        t_stats = metrics["tasks"]
        
        total_m = sum(m_stats.values())
        if total_m == 0: return "Error: No data available for health calculation."
        
        completed_on_time = m_stats.get("on-time", 0) # Assuming 'on-time' is the state of healthy milestone
        delayed_m = m_stats.get("delayed", 0)
        blocked_tasks = t_stats.get("blocked", 0)
        
        progress_pct = (completed_on_time / total_m) * 100
        
        # Health Logic
        if progress_pct > 80 and blocked_tasks == 0:
            color, symbol = "GREEN", "🟢"
        elif progress_pct >= 50 and blocked_tasks < 3:
            color, symbol = "AMBER", "🟡"
        else:
            color, symbol = "RED", "🔴"
            
        risks = []
        if delayed_m > 0: risks.append(f"{delayed_m} milestones are currently delayed.")
        if blocked_tasks > 0: risks.append(f"{blocked_tasks} tasks are currently blocked.")
        
        risk_str = "\n".join([f"- {r}" for r in risks]) if risks else "No major risks identified."
        
        return f"""### Project Health Report: {project_id}
Status: {symbol} **{color}**
Overall Progress: {progress_pct:.1f}%

**Risk Summary:**
{risk_str}
"""
    except Exception as e:
        return f"Error computing health: {str(e)}"


# --- Chat Integration Tool ---

@tool
def get_project_pulse(project_name_or_id: str) -> str:
    """
    Retrieves the current 'pulse' (health, progress, and risks) for a specific project.
    Input: project_name_or_id
    Returns: A detailed health report formatted for chat.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name FROM projects WHERE id = ? OR name LIKE ?",
                (project_name_or_id, f"%{project_name_or_id}%"),
            )
            row = cur.fetchone()
            if not row:
                return f"I couldn't find any project matching '{project_name_or_id}'."
            
            project_id, name = row[0], row[1]
            health_report = compute_project_health.invoke({"project_id": project_id})
            return f"Pulse Check for **{name}** ({project_id}):\n\n{health_report}"
    except Exception as e:
        return f"Error fetching pulse: {str(e)}"
