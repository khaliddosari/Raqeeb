"""The authority call is Arabic end to end, and its transcript streams to the dashboard live.

Two promises are held here. First, nothing the model is given for the call is English, so it
has no English to repeat on the line; the only Latin text allowed in the instructions is the
tool's function name (an API identifier, never spoken) and the incident reference code.
Second, the live transcript orders turns the way they were spoken, even though the Realtime
API often finishes transcribing the authority after the agent has started replying."""

from __future__ import annotations

import re

from agent import monitor
from agent.authority_mapping import get_authority_for_class
from agent.checkpoints import CHECKPOINTS, scenario_for
from agent.voice.authority_prompts import RECORD_DISPATCH_CONFIRMATION_TOOL, build_dispatch_instructions
from agent.voice.sip_authority_call import LiveTranscript

_LATIN = re.compile(r"[A-Za-z]")

_REPORT = {
    "incident_id": "INC-20260914-81127F",
    "date_time": "2026-09-14T11:06:29+03:00",
    "location": "Money20/20 Middle East",
    "detected_item": "Gun",
    "employee": {"name": "خالد آل دوسري", "id": "+966551234567"},
    "suspect": {"name": "فيصل", "id_number": "093847562"},
    "scenario": scenario_for("Money20/20 Middle East"),
}


def test_call_instructions_carry_no_english():
    authority = get_authority_for_class("Gun").model_dump()
    prompt = build_dispatch_instructions(_REPORT["incident_id"], _REPORT, authority)

    expected_text = ("موني عشرين عشرين", "سلاح ناري", "الشرطة", "وحدة الاستجابة المسلحة", "14 سبتمبر 2026",
                     "صندوق معدات أسود بعجلات", "رصيف التحميل الخلفي")
    for expected in expected_text:
        assert expected in prompt, expected

    leftover = prompt.replace(RECORD_DISPATCH_CONFIRMATION_TOOL.name, "").replace(_REPORT["incident_id"], "")
    assert not _LATIN.findall(leftover), sorted(set(_LATIN.findall(leftover)))


def test_every_checkpoint_speaks_arabic_and_has_a_scenario():
    """The agent says these names and may be asked any of these details, so none may be Latin."""
    assert len({c.pass_slug for c in CHECKPOINTS}) == len(CHECKPOINTS)
    assert len({c.suspect.id_number for c in CHECKPOINTS}) == len(CHECKPOINTS)
    for checkpoint in CHECKPOINTS:
        assert not _LATIN.search(checkpoint.spoken_ar), checkpoint.code
        assert len(checkpoint.scenario) >= 8, checkpoint.code
        for label, detail in checkpoint.scenario:
            assert not _LATIN.search(label + detail), (checkpoint.code, label)
        # the scanned pass's name and number reach the call as the suspect's details
        assert not _LATIN.search(checkpoint.suspect.name + checkpoint.suspect.pass_type), checkpoint.code
        # nine digits behind a leading zero, which no real Saudi ID can be: those are ten digits
        # starting with 1 or 2, so a demo number cannot land on a real person's
        suspect_id = checkpoint.suspect.id_number
        assert suspect_id.isdigit() and len(suspect_id) == 9 and suspect_id.startswith("0"), checkpoint.code


def test_tool_definition_is_arabic_apart_from_identifiers():
    tool = RECORD_DISPATCH_CONFIRMATION_TOOL
    texts = [tool.description] + [p["description"] for p in tool.parameters["properties"].values()]
    assert all(not _LATIN.search(text) for text in texts)


def test_tools_route_calls_to_the_matching_agency_in_arabic():
    tools_prompt = build_dispatch_instructions("INC-1", {**_REPORT, "detected_item": "Wrench"}, get_authority_for_class("Wrench").model_dump())
    assert "أمن المطار" in tools_prompt and "مفتاح ربط" in tools_prompt and "الشرطة" not in tools_prompt


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_live_transcript_orders_turns_as_spoken_and_updates_lines_in_place():
    incident_id = "TEST-LIVE-TRANSCRIPT-1"
    monitor.clear(incident_id)
    clock = _Clock()
    live = LiveTranscript(incident_id, clock=clock)

    # the agent opens, word by word
    live.handle({"type": "response.output_item.added", "item": {"type": "message", "id": "a1"}})
    live.handle({"type": "response.output_audio_transcript.delta", "item_id": "a1", "delta": "السلام عليكم، "})
    clock.now = 0.05  # inside the throttle window: not republished yet
    live.handle({"type": "response.output_audio_transcript.delta", "item_id": "a1", "delta": "معك رقيب"})
    live.handle({"type": "response.output_audio_transcript.done", "item_id": "a1", "transcript": "السلام عليكم، معك رقيب"})

    # the authority answers; the agent starts replying before that answer is transcribed
    live.handle({"type": "input_audio_buffer.committed", "item_id": "u1"})
    live.handle({"type": "response.output_item.added", "item": {"type": "message", "id": "a2"}})
    clock.now = 1.0
    live.handle({"type": "response.output_audio_transcript.delta", "item_id": "a2", "delta": "تمام، "})
    live.handle({"type": "conversation.item.input_audio_transcription.completed", "item_id": "u1", "transcript": "وعليكم السلام، تفضل"})
    # a function call item is not a transcript line
    assert not live.handle({"type": "response.output_item.added", "item": {"type": "function_call", "id": "f1"}})

    live.flush()  # the call ends mid-sentence

    assert live.lines() == [
        {"role": "assistant", "text": "السلام عليكم، معك رقيب"},
        {"role": "authority", "text": "وعليكم السلام، تفضل"},
        {"role": "assistant", "text": "تمام،"},
    ]

    queue = monitor.subscribe(incident_id)
    replayed = []
    while not queue.empty():
        replayed.append(queue.get_nowait())
    monitor.unsubscribe(incident_id, queue)

    # a late subscriber gets exactly one, finished, entry per line, each with its spoken position
    by_item = {event["item_id"]: event for event in replayed}
    assert len(replayed) == 3
    assert [by_item[i]["seq"] for i in ("a1", "u1", "a2")] == [0, 1, 2]
    assert all(event["final"] for event in replayed)
    assert by_item["u1"]["role"] == "authority"
