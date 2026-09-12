"""The LangGraph workflow: orchestration + state management only. Every external
side-effect (YOLO inference, Gemini calls, Twilio calls, HTTP delivery) is delegated to
agent/*.py modules; nodes here just call those and shuffle state.

Human-in-the-loop points (employee_verification, collect_incident_information,
gemini_authority_conversation) use LangGraph's interrupt()/Command(resume=...) pattern:
graph.invoke() runs until it hits an interrupt and returns the interrupt payload to the
caller (a FastAPI route), which later resumes the same thread_id with the human's/voice
session's answer.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from agent.authority_mapping import get_authority_for_class
from agent.config import settings
from agent.graph.state import IncidentState
from agent.providers.factory import get_llm_provider, get_telephony_provider
from agent.report import generate_report, missing_required_fields
from agent.report_delivery import send_report
from agent.schemas import AuthorityConfig
from agent.yolo_detector import get_detector

# --- Nodes -------------------------------------------------------------------


async def yolo_detection_node(state: IncidentState) -> dict[str, Any]:
    if state.get("detection_class") is not None:
        return {}
    result = get_detector().detect(state["image_path"], annotate=True)
    return {"detection_class": result.detected_class, "detection_confidence": result.confidence, "status": "detected"}


async def display_detection_node(state: IncidentState) -> dict[str, Any]:
    return {"status": "pending_verification"}


async def employee_verification_node(state: IncidentState) -> dict[str, Any]:
    decision = interrupt(
        {
            "stage": "employee_verification",
            "detection_class": state["detection_class"],
            "detection_confidence": state["detection_confidence"],
            # Already known from the shift login + checkpoint config; shown to the
            # employee for confirmation, never re-entered.
            "location": state.get("incident_data", {}).get("location"),
            "employee_name": state.get("employee_name"),
            "employee_id": state.get("employee_id"),
        }
    )
    confirmed = bool(decision["confirmed"])
    incident_data = dict(state.get("incident_data", {}))
    if decision.get("notes"):
        incident_data["employee_notes"] = decision["notes"]
    return {
        "verification_status": "confirmed" if confirmed else "false_positive",
        "verification_channel": "dashboard_button",
        "incident_data": incident_data,
        "status": "verified" if confirmed else "false_positive",
    }


def route_after_verification(state: IncidentState) -> str:
    return "false_positive_end" if state["verification_status"] == "false_positive" else "collect_incident_information"


async def false_positive_end_node(state: IncidentState) -> dict[str, Any]:
    return {"status": "false_positive"}


async def collect_incident_information_node(state: IncidentState) -> dict[str, Any]:
    answer = interrupt(
        {
            "stage": "collect_information",
            "required_fields": list(settings.required_incident_fields),
            "already_collected": state.get("incident_data", {}),
        }
    )
    if answer.get("flagged_false_positive"):
        # The employee said out loud, mid-conversation, that this was a false alarm --
        # still the employee's decision, Gemini is only relaying it, not overriding.
        return {"verification_status": "false_positive", "status": "false_positive"}
    merged = {**state.get("incident_data", {}), **answer.get("fields", {})}
    return {"incident_data": merged, "status": "collecting_information"}


def route_after_collection(state: IncidentState) -> str:
    return "false_positive_end" if state["verification_status"] == "false_positive" else "validate_information"


async def validate_information_node(state: IncidentState) -> dict[str, Any]:
    missing = missing_required_fields(state.get("incident_data", {}))
    return {"status": "awaiting_more_information" if missing else "information_validated"}


def route_after_validation(state: IncidentState) -> str:
    return (
        "collect_incident_information" if state["status"] == "awaiting_more_information" else "generate_incident_report"
    )


async def generate_incident_report_node(state: IncidentState) -> dict[str, Any]:
    llm = get_llm_provider()
    report, summary = await generate_report(
        incident_id=state["incident_id"],
        detection_class=state["detection_class"],
        detection_confidence=state["detection_confidence"],
        verification_status=state["verification_status"],
        incident_data=state["incident_data"],
        llm=llm,
    )
    return {"report": report.model_dump(), "report_summary": summary, "status": "report_generated"}


async def determine_authority_node(state: IncidentState) -> dict[str, Any]:
    authority = get_authority_for_class(state["detection_class"])
    return {"authority": authority.model_dump(), "status": "authority_determined"}


async def send_report_node(state: IncidentState) -> dict[str, Any]:
    authority = AuthorityConfig(**state["authority"])
    ok = await send_report(authority, state["report"])
    return {"status": "report_sent" if ok else "report_send_failed"}


async def twilio_outbound_call_node(state: IncidentState) -> dict[str, Any]:
    telephony = get_telephony_provider()
    authority = AuthorityConfig(**state["authority"])
    call_sid = await telephony.place_call(authority.phone_number, state["incident_id"])
    return {"call_sid": call_sid, "status": "call_in_progress"}


async def gemini_authority_conversation_node(state: IncidentState) -> dict[str, Any]:
    result = interrupt(
        {
            "stage": "authority_conversation",
            "call_sid": state.get("call_sid"),
            "report_summary": state.get("report_summary"),
            "report": state.get("report"),
        }
    )
    return {"authority_response": result, "status": "authority_responded"}


async def update_incident_node(state: IncidentState) -> dict[str, Any]:
    confirmed = bool((state.get("authority_response") or {}).get("dispatch_confirmed"))
    return {"status": "closed" if confirmed else "closed_unconfirmed"}


# --- Graph assembly ------------------------------------------------------------


def build_graph():
    graph = StateGraph(IncidentState)

    graph.add_node("yolo_detection", yolo_detection_node)
    graph.add_node("display_detection", display_detection_node)
    graph.add_node("employee_verification", employee_verification_node)
    graph.add_node("false_positive_end", false_positive_end_node)
    graph.add_node("collect_incident_information", collect_incident_information_node)
    graph.add_node("validate_information", validate_information_node)
    graph.add_node("generate_incident_report", generate_incident_report_node)
    graph.add_node("determine_authority", determine_authority_node)
    graph.add_node("send_report", send_report_node)
    graph.add_node("twilio_outbound_call", twilio_outbound_call_node)
    graph.add_node("gemini_authority_conversation", gemini_authority_conversation_node)
    graph.add_node("update_incident", update_incident_node)

    graph.set_entry_point("yolo_detection")
    graph.add_edge("yolo_detection", "display_detection")
    graph.add_edge("display_detection", "employee_verification")
    graph.add_conditional_edges(
        "employee_verification",
        route_after_verification,
        {"false_positive_end": "false_positive_end", "collect_incident_information": "collect_incident_information"},
    )
    graph.add_conditional_edges(
        "collect_incident_information",
        route_after_collection,
        {"false_positive_end": "false_positive_end", "validate_information": "validate_information"},
    )
    graph.add_conditional_edges(
        "validate_information",
        route_after_validation,
        {
            "collect_incident_information": "collect_incident_information",
            "generate_incident_report": "generate_incident_report",
        },
    )
    graph.add_edge("generate_incident_report", "determine_authority")
    graph.add_edge("determine_authority", "send_report")
    graph.add_edge("send_report", "twilio_outbound_call")
    graph.add_edge("twilio_outbound_call", "gemini_authority_conversation")
    graph.add_edge("gemini_authority_conversation", "update_incident")
    graph.add_edge("update_incident", END)
    graph.add_edge("false_positive_end", END)

    return graph.compile(checkpointer=MemorySaver())


# Single shared compiled graph + checkpointer for the process. Swap MemorySaver for a
# persistent checkpointer (e.g. SqliteSaver/PostgresSaver) in production so incidents
# survive a restart while paused on an interrupt.
compiled_graph = build_graph()


def thread_config(incident_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": incident_id}}
