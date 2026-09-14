"""Read-only live feed for the dashboard: call transcript turns, status changes and the
dispatch decision, as they happen. Accepts nothing from the client."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent import monitor
from agent.graph.runner import get_incident_snapshot

router = APIRouter(tags=["monitor"])

_HEARTBEAT_SECONDS = 20


@router.websocket("/ws/monitor/{incident_id}")
async def monitor_incident(websocket: WebSocket, incident_id: str) -> None:
    await websocket.accept()
    queue = monitor.subscribe(incident_id)

    try:
        snapshot = await get_incident_snapshot(incident_id)
        await websocket.send_json({"type": "snapshot", "status": snapshot.values.get("status")})
    except Exception:
        # An incident the graph has never seen is not an error worth closing over; the
        # dashboard may simply have opened the socket first.
        await websocket.send_json({"type": "snapshot", "status": None})

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                # Keeps intermediaries from dropping an idle socket during a long call.
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        monitor.unsubscribe(incident_id, queue)
