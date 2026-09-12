"""Sends the generated report to the authority's configured endpoint. Pure I/O -- no
decision-making happens here, the authority was already determined upstream."""

from __future__ import annotations

from typing import Any

import httpx

from agent.config import is_mock_llm
from agent.schemas import AuthorityConfig


async def send_report(authority: AuthorityConfig, report: dict[str, Any]) -> bool:
    if is_mock_llm() or authority.report_endpoint.startswith("https://example-authority.local"):
        # No real authority system configured yet -- treat as delivered so the
        # workflow can be exercised end-to-end. Point report_endpoint at a real
        # webhook/API in config/authority_mapping.yaml to actually deliver reports.
        return True

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(authority.report_endpoint, json=report)
            return response.status_code < 300
    except httpx.HTTPError:
        # An unreachable authority must not strand the incident: the caller records
        # report_send_failed and the graph still goes on to place the dispatch call,
        # which is the half that actually gets a team moving.
        return False
