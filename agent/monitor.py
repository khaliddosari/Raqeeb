"""Live monitoring fan-out for the dashboard.

The authority call already accumulates a transcript, but only hands it back when the
call ends. This lets the dashboard watch it turn by turn instead. Publishing is
fire-and-forget: a slow or dead subscriber is dropped rather than allowed to stall the
call, because nothing here may ever block the audio path.

State is per-process. With more than one replica a subscriber only sees calls handled by
its own container, so this needs a real broker (Redis pub/sub) before scaling out.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

_MAX_QUEUED = 64

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_history: dict[str, list[dict[str, Any]]] = defaultdict(list)


def subscribe(incident_id: str) -> asyncio.Queue:
    """Returns a queue pre-loaded with everything already published for this incident,
    so a dashboard opened mid-call still renders the turns it missed."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUED)
    for event in _history[incident_id]:
        queue.put_nowait(event)
    _subscribers[incident_id].add(queue)
    return queue


def unsubscribe(incident_id: str, queue: asyncio.Queue) -> None:
    _subscribers[incident_id].discard(queue)
    if not _subscribers[incident_id]:
        _subscribers.pop(incident_id, None)


def publish(incident_id: str, event: dict[str, Any]) -> None:
    history = _history[incident_id]
    item_id = event.get("item_id")
    # A live transcript line is republished with its whole text every time it grows. History
    # keeps only its latest version, so a dashboard joining mid-call replays one entry per
    # line rather than every intermediate word, and the 200-event cap is not eaten by one turn.
    for index in range(len(history) - 1, -1, -1) if item_id is not None else ():
        if history[index].get("item_id") == item_id and history[index].get("type") == event.get("type"):
            history[index] = event
            break
    else:
        history.append(event)
    del history[:-200]
    for queue in list(_subscribers[incident_id]):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            _subscribers[incident_id].discard(queue)


def publish_transcript(
    incident_id: str,
    role: str,
    text: str,
    *,
    item_id: str | None = None,
    seq: int | None = None,
    final: bool = True,
) -> None:
    """item_id and seq identify a line that is still being spoken: the dashboard replaces the
    line with the same item_id and orders lines by seq. Without them the line is appended."""
    event: dict[str, Any] = {"type": "transcript", "role": role, "text": text, "final": final}
    if item_id is not None:
        event["item_id"] = item_id
        event["seq"] = seq
    publish(incident_id, event)


def publish_status(incident_id: str, status: str, **extra: Any) -> None:
    publish(incident_id, {"type": "status", "status": status, **extra})


def clear(incident_id: str) -> None:
    _history.pop(incident_id, None)
