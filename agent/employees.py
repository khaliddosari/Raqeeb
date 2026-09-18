"""The on-duty employees a run can be filed under.

Deliberately no phone numbers here. The dashboard is public, so its bundle may not carry a
personal number, and this file is in a public repository, so neither may it. The number the
dispatch call rings lives only in the environment, as ADMIN_CALL_NUMBERS
("khalid=+9665XXXXXXXX,yazeed=+9665XXXXXXXX"), and is read here on the admin path alone.

A public visitor picks the same people and gets the same report; there is simply no phone call
to place, because the conversation happens in their own browser instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import settings
from agent.intake import normalize_saudi_mobile


@dataclass(frozen=True)
class Employee:
    key: str
    name_ar: str
    name_en: str
    badge: str
    """The staff number printed on the report, which used to be the employee's mobile."""


EMPLOYEES: tuple[Employee, ...] = (
    Employee(key="khalid", name_ar="خالد آل دوسري", name_en="Khalid Al Dosari", badge="10453"),
    Employee(key="yazeed", name_ar="يزيد بن شيحة", name_en="Yazeed Bin Shihah", badge="10461"),
    Employee(key="nawaf", name_ar="نواف الشهراني", name_en="Nawaf Alsharani", badge="10478"),
    Employee(key="omar", name_ar="عمر الضويان", name_en="Omar Al-Dhawyan", badge="10486"),
)

BY_KEY: dict[str, Employee] = {employee.key: employee for employee in EMPLOYEES}


def call_numbers() -> dict[str, str]:
    """The employee keys that have a number to ring, from ADMIN_CALL_NUMBERS. A malformed
    entry is dropped rather than raising: one bad pair must not stop the server booting, and
    the admin path reports the missing number when the call is actually attempted."""
    numbers: dict[str, str] = {}
    for pair in settings.admin_call_numbers.split(","):
        key, _, raw = pair.partition("=")
        key, raw = key.strip(), raw.strip()
        if not key or not raw or key not in BY_KEY:
            continue
        try:
            numbers[key] = normalize_saudi_mobile(raw)
        except ValueError:
            continue
    return numbers


def roster(*, with_numbers: bool = False) -> list[dict[str, object]]:
    """What the dashboard shows in its employee picker. `with_numbers` only ever says whether a
    number is configured, never what it is: the dashboard has no use for the digits."""
    configured = call_numbers() if with_numbers else {}
    return [
        {
            "key": employee.key,
            "name_ar": employee.name_ar,
            "name_en": employee.name_en,
            "badge": employee.badge,
            **({"has_number": employee.key in configured} if with_numbers else {}),
        }
        for employee in EMPLOYEES
    ]
