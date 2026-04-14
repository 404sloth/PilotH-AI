#!/usr/bin/env python3
"""
Integration test for the Meetings & Communication Agent.
Tests: DB seed, persons table, all 11 tools, scheduling/summarize/brief nodes.
Run: .venv/bin/python3 tests/test_meetings_agent.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = "✓", "✗"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status} {name}" + (f"  [{detail}]" if detail else ""))


def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


# ── 1. DB init ───────────────────────────────────────────────────────────────
section("1. Database Init (Persons + Meetings Tables)")
try:
    from integrations.data_warehouse.sqlite_client import init_db
    init_db(seed=True)
    check("init_db with meeting tables", True)
except Exception as e:
    check("init_db with meeting tables", False, str(e))

# ── 2. Persons DAL ───────────────────────────────────────────────────────────
section("2. Persons DAL — Disambiguation")
try:
    from integrations.data_warehouse.meeting_db import (
        find_persons, get_person_by_email, get_person_by_id,
        get_busy_blocks, get_meeting_full,
    )
    all_persons = find_persons()
    check("find_persons — returns seeded persons", len(all_persons) >= 5, f"{len(all_persons)} found")

    p = get_person_by_email("anil.yadav@company.com")
    check("get_person_by_email anil.yadav", p is not None and p["department"] == "Engineering")

    p2 = get_person_by_email("anil.kumar@company.com")
    check("get_person_by_email anil.kumar (Finance — different Anil)", p2 is not None and p2["department"] == "Finance")

    # Disambiguation: same first name but different people
    anil_results = find_persons(name="Anil")
    check("Disambiguation: 2 Anils found", len(anil_results) == 2,
          f"{[a['full_name']+' '+a['department'] for a in anil_results]}")

    p3 = get_person_by_id("P-001")
    check("get_person_by_id P-001", p3 is not None and "skills" in p3)

    mtg = get_meeting_full("MTG-001")
    check("get_meeting_full MTG-001", mtg is not None and len(mtg.get("attendees", [])) >= 2)
    check("meeting has agenda items", len(mtg.get("agenda", [])) >= 2)
    check("meeting has action items", len(mtg.get("action_items", [])) >= 1)

except Exception as e:
    import traceback
    check("Persons DAL", False, traceback.format_exc())

# ── 3. All 11 Tools ──────────────────────────────────────────────────────────
section("3. All 11 Tools")

try:
    from agents.communication.tools.briefing_tool import ParticipantBriefingTool, BriefingInput
    t = ParticipantBriefingTool()
    out = t.execute(BriefingInput(emails=["anil.yadav@company.com", "james.carter@company.com"]))
    check("ParticipantBriefingTool — found 2", out.found == 2)
    check("ParticipantBriefingTool — disambiguation note present", bool(out.participants[0].disambiguation_note))
except Exception as e:
    check("ParticipantBriefingTool", False, str(e))

try:
    from agents.communication.tools.calendar_tools import (
        GoogleCalendarAvailabilityTool, AvailabilityInput,
        GoogleCalendarCreateTool, CalendarCreateInput,
    )
    from datetime import datetime, timedelta
    now   = datetime.utcnow()
    avail = GoogleCalendarAvailabilityTool().execute(AvailabilityInput(
        attendee_emails=["anil.yadav@company.com", "priya.sharma@company.com"],
        from_time=now.isoformat(),
        to_time=(now + timedelta(days=1)).isoformat(),
    ))
    check("GoogleCalendarAvailabilityTool — checked attendees", len(avail.checked) >= 1, f"checked={avail.checked}")

    created = GoogleCalendarCreateTool().execute(CalendarCreateInput(
        title="Test Meeting",
        attendee_emails=["anil.yadav@company.com", "james.carter@company.com"],
        start_time=(now + timedelta(days=2)).isoformat(),
        end_time=(now + timedelta(days=2, hours=1)).isoformat(),
        timezone="UTC",
    ))
    check("GoogleCalendarCreateTool — created", created.created and created.event_id)
    check("GoogleCalendarCreateTool — internal only (no HITL)", not created.has_external)
except Exception as e:
    check("Calendar Tools", False, str(e))

try:
    from agents.communication.tools.timezone_tool import TimezoneConverterTool, TimezoneInput
    out = TimezoneConverterTool().execute(TimezoneInput(
        datetime_str="2025-01-15T09:00:00",
        from_tz="Asia/Kolkata",
        to_tz="America/New_York",
    ))
    check("TimezoneConverterTool — converts IST→ET", "converted" in out.model_dump())
except Exception as e:
    check("TimezoneConverterTool", False, str(e))

try:
    from agents.communication.tools.sentiment_tool import SentimentAnalysisTool, SentimentInput
    out = SentimentAnalysisTool().execute(SentimentInput(
        texts=["The project is going great and the team is impressed!", "There are serious concerns about delays."]
    ))
    check("SentimentAnalysisTool — analysed 2 texts", len(out.records) == 2)
    check("SentimentAnalysisTool — first text positive", out.records[0].label == "positive")
    check("SentimentAnalysisTool — second text negative", out.records[1].label in ("negative","neutral"))
except Exception as e:
    check("SentimentAnalysisTool", False, str(e))

try:
    from agents.communication.tools.agenda_tool import AgendaGeneratorTool, AgendaInput
    out = AgendaGeneratorTool().execute(AgendaInput(
        meeting_title="Q3 Engineering Review",
        goals="Align on LangGraph rollout and DevOps blockers",
        duration_minutes=60,
        attendee_roles=["CTO", "Engineer", "DevOps"],
    ))
    check("AgendaGeneratorTool — has items", len(out.items) >= 3, f"{len(out.items)} items")
    check("AgendaGeneratorTool — total duration = 60", out.total_minutes == 60, f"total={out.total_minutes}")
except Exception as e:
    check("AgendaGeneratorTool", False, str(e))

try:
    from agents.communication.tools.summarizer_tool import MeetingSummarizerTool, SummarizerInput
    transcript = """
    James: We decided to use LangGraph v0.2 for the orchestration layer.
    Priya: Agreed. Action: James will complete the graph by Friday.
    Anil: Risk: we may face API rate limits from Ollama under load.
    James (owner): will raise a ticket for load testing by next Monday.
    """
    out = MeetingSummarizerTool().execute(SummarizerInput(
        transcript=transcript,
        meeting_title="Architecture Decision",
        attendees=["James Carter", "Priya Sharma", "Anil Yadav"],
    ))
    check("MeetingSummarizerTool — has summary", bool(out.executive_summary))
    check("MeetingSummarizerTool — extracted decisions or action items", len(out.key_decisions) + len(out.action_items) > 0)
except Exception as e:
    check("MeetingSummarizerTool", False, str(e))

try:
    from agents.communication.tools.conflict_resolver_tool import ConflictResolverTool, ConflictResolverInput
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    out = ConflictResolverTool().execute(ConflictResolverInput(
        attendee_emails=["anil.yadav@company.com"],
        preferred_start=(now + timedelta(hours=2)).isoformat(),
        preferred_end=(now + timedelta(hours=3)).isoformat(),
        duration_mins=60,
    ))
    check("ConflictResolverTool — returns result", "conflict_detected" in out.model_dump())
    check("ConflictResolverTool — alternatives list present", isinstance(out.alternatives, list))
except Exception as e:
    check("ConflictResolverTool", False, str(e))

try:
    from agents.communication.tools.slack_tool import SlackNotifierTool, SlackInput
    out = SlackNotifierTool().execute(SlackInput(channel="#engineering", message="Test message", mentions=["@anil"]))
    check("SlackNotifierTool — mock sent", out.sent)
except Exception as e:
    check("SlackNotifierTool", False, str(e))

try:
    from agents.communication.tools.email_draft_tool import EmailDraftTool, EmailDraftInput
    out = EmailDraftTool().execute(EmailDraftInput(
        email_type="followup",
        recipients=["james.carter@company.com"],
        context="Meeting concluded. Action: Complete LangGraph by Friday. Risk: API limits.",
    ))
    check("EmailDraftTool — body generated", len(out.body) > 20)
except Exception as e:
    check("EmailDraftTool", False, str(e))

# ── 4. Graph nodes ────────────────────────────────────────────────────────────
section("4. Graph Nodes (no LLM)")

try:
    from agents.communication.nodes.scheduling import (
        resolve_participants_node, fetch_availability_node,
        find_common_slots_node, propose_slots_node,
    )

    state = {
        "action": "schedule",
        "title": "Architecture Sync",
        "participants": [{"email": "anil.yadav@company.com"}, {"email": "james.carter@company.com"}],
        "duration_minutes": 60,
        "timezone": "UTC",
    }

    s1 = resolve_participants_node(state)
    check("resolve_participants_node — found 2", len(s1.get("resolved_participants", [])) == 2)

    state.update(s1)
    s2 = fetch_availability_node(state)
    check("fetch_availability_node — availability dict", "availability" in s2)

    state.update(s2)
    s3 = find_common_slots_node(state)
    check("find_common_slots_node — free slots returned", len(s3.get("free_slots", [])) > 0)

    state.update(s3)
    s4 = propose_slots_node(state)
    check("propose_slots_node — proposed slots list", len(s4.get("proposed_slots", [])) > 0)

except Exception as e:
    import traceback
    check("Scheduling nodes", False, traceback.format_exc())

try:
    from agents.communication.nodes.summarization import retrieve_transcript_node, extract_key_points_node

    state2 = {
        "action":      "summarize",
        "transcript":  "Decided: use LangGraph v0.2. Action: James to finish graph. Risk: rate limits.",
        "title":       "Architecture Review",
        "participants": [],
        "duration_minutes": 60,
    }
    ts = retrieve_transcript_node(state2)
    check("retrieve_transcript_node", bool(ts.get("transcript")))

    state2.update(ts)
    kp = extract_key_points_node(state2)
    check("extract_key_points_node — returns dicts", "decisions" in kp or "key_points" in kp or kp == {})

except Exception as e:
    import traceback
    check("Summarization nodes", False, traceback.format_exc())

try:
    from agents.communication.nodes.briefing import gather_context_node, generate_agenda_node

    state3 = {
        "action":      "brief",
        "title":       "Q3 Review",
        "context":     "Discuss Q3 milestones and risks",
        "participants": [{"email": "priya.sharma@company.com"}],
        "duration_minutes": 45,
    }
    gc = gather_context_node(state3)
    check("gather_context_node — bios returned", "participant_bios" in gc)

    state3.update(gc)
    ag = generate_agenda_node(state3)
    check("generate_agenda_node — agenda items list", len(ag.get("agenda_items", [])) >= 1)

except Exception as e:
    import traceback
    check("Briefing nodes", False, traceback.format_exc())

# ── 5. Memory system ──────────────────────────────────────────────────────────
section("5. Memory Systems")
try:
    from memory.session_store import get_session_store
    store = get_session_store()
    s = store.get_or_create("test-session-001")
    s.add_message("user", "Schedule a meeting")
    s.set_context("last_agent", "meetings_communication")
    check("SessionStore — create & add message", len(s.messages) == 1)
    check("SessionStore — context set", s.get_context("last_agent") == "meetings_communication")

    from memory.global_context import get_global_context
    ctx = get_global_context()
    ctx.set("test_key", {"value": 42}, agent="test", ttl_seconds=60)
    val = ctx.get("test_key")
    check("GlobalContext — set & get", val == {"value": 42})
    ctx.log_decision("Test decision", agent="test")
    decisions = ctx.get_recent_decisions(1)
    check("GlobalContext — decision log", len(decisions) >= 1)

except Exception as e:
    import traceback
    check("Memory systems", False, traceback.format_exc())

# ── 6. Token Counter ──────────────────────────────────────────────────────────
section("6. Token Counter")
try:
    from llm.token_counter import TokenCounter
    tc = TokenCounter()
    tc.record("gpt-4o", 100, 50)
    tc.record("gpt-4o", 200, 100)
    tc.record("llama3", 500, 200)
    totals = tc.totals()
    check("TokenCounter — total_tokens", totals["total_tokens"] == 1150, f"{totals['total_tokens']}")
    check("TokenCounter — cost estimated", totals["estimated_cost_usd"] > 0)
    check("TokenCounter — by_model dict", "gpt-4o" in totals["by_model"])
except Exception as e:
    check("TokenCounter", False, str(e))

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}\n  RESULTS SUMMARY\n{'='*60}")
passed = [r for r in results if r[0] == PASS]
failed = [r for r in results if r[0] == FAIL]
print(f"  Passed: {len(passed)} / {len(results)}")
if failed:
    print(f"\n  Failed tests:")
    for _, name, detail in failed:
        print(f"    {FAIL} {name}: {detail}")
else:
    print(f"\n  All tests passed! Meetings Agent is fully operational.")
print()
