"""What the dashboard sends with a detection. The phone number is dialled by the telephony
provider and the location is read out to an authority, so both must be refused unless they
match the closed formats in agent/intake.py."""

from __future__ import annotations

import pytest

from agent.authority_mapping import get_authority_for_class
from agent.intake import CHECKPOINT_LOCATIONS, normalize_saudi_mobile, validate_location


@pytest.mark.parametrize(
    "raw",
    ["0551234567", "551234567", "+966551234567", "966551234567", "055 123 4567", "055-123-4567"],
)
def test_saudi_mobile_forms_normalize_to_e164(raw):
    assert normalize_saudi_mobile(raw) == "+966551234567"


@pytest.mark.parametrize(
    "raw",
    ["0112345678", "+14155550100", "05512345", "05512345678", "0551234567;+14155550100", "", "abc"],
)
def test_non_saudi_mobiles_are_refused(raw):
    with pytest.raises(ValueError):
        normalize_saudi_mobile(raw)


def test_only_known_checkpoints_are_accepted():
    for location in CHECKPOINT_LOCATIONS:
        assert validate_location(location) == location
    with pytest.raises(ValueError):
        validate_location("Terminal 6")


def test_weapons_route_to_police_and_tools_to_airport_security():
    assert {get_authority_for_class(c).agency for c in ("Gun", "Knife")} == {"police"}
    assert {get_authority_for_class(c).agency for c in ("Pliers", "Scissors", "Wrench")} == {"airport_security"}
