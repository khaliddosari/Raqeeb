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
    _history[incident_id].append(event)
    del _history[incident_id][:-200]
    for queue in list(_subscribers[incident_id]):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            _subscribers[incident_id].discard(queue)


def publish_transcript(incident_id: str, role: str, text: str) -> None:
    publish(incident_id, {"type": "transcript", "role": role, "text": text})


def publish_status(incident_id: str, status: str, **extra: Any) -> None:
    publish(incident_id, {"type": "status", "status": status, **extra})


def clear(incident_id: str) -> None:
    _history.pop(incident_id, None)
