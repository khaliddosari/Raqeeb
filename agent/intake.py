"""Validation for what the dashboard sends with a detection: the on-duty employee's mobile
number, which takes the dispatch call, and the checkpoint the frame came from.

Both end up somewhere sensitive (a number the telephony provider dials, a place the voice
agent reads out to an authority), so both are checked against a closed set here rather than
passed through as free text.
"""

from __future__ import annotations

import re

from agent.checkpoints import CHECKPOINTS

# The checkpoints a frame can come from, defined with their scenarios in agent/checkpoints.py.
# The dashboard sends these exact codes and translates them for display.
CHECKPOINT_LOCATIONS: tuple[str, ...] = tuple(checkpoint.code for checkpoint in CHECKPOINTS)

# Saudi mobiles are 5 followed by eight digits, written as 05XXXXXXXX locally or with the
# 966 country code. Landlines and foreign numbers are refused.
_SAUDI_MOBILE = re.compile(r"^(?:\+?966|0)?(5\d{8})$")


def normalize_saudi_mobile(raw: str) -> str:
    """Returns the number in E.164 (+9665XXXXXXXX), or raises ValueError."""
    compact = re.sub(r"[\s\-()]", "", raw)
    match = _SAUDI_MOBILE.match(compact)
    if not match:
        raise ValueError("Enter a Saudi mobile number, such as 0551234567.")
    return f"+966{match.group(1)}"


def validate_location(raw: str) -> str:
    if raw not in CHECKPOINT_LOCATIONS:
        raise ValueError(f"Unknown checkpoint location. Expected one of: {', '.join(CHECKPOINT_LOCATIONS)}.")
    return raw
