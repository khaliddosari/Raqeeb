"""Arabic renderings of the codes an incident carries, for everything said on or shown about
the authority call. The codes themselves (Gun, Black Hat MEA, police) stay the storage format;
these are the words used in their place. Classes and agencies match the dashboard's Arabic
dictionary in frontend/src/lib/i18n.ts; checkpoint names are the spoken forms from
agent/checkpoints.py, which transliterate the Latin brand names the dashboard shows."""

from __future__ import annotations

import datetime

from agent.checkpoints import CHECKPOINTS

DETECTION_CLASSES_AR: dict[str, str] = {
    "Gun": "سلاح ناري",
    "Knife": "سكين",
    "Pliers": "كماشة",
    "Scissors": "مقص",
    "Wrench": "مفتاح ربط",
}

# Spoken forms, in Arabic script even where the dashboard writes a Latin brand name, because these
# are what the voice agent says aloud.
CHECKPOINT_LOCATIONS_AR: dict[str, str] = {checkpoint.code: checkpoint.spoken_ar for checkpoint in CHECKPOINTS}

AGENCIES_AR: dict[str, str] = {
    "police": "الشرطة",
    "airport_security": "أمن المطار",
}

_MONTHS_AR = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)


def detection_class_ar(value: str | None) -> str:
    return DETECTION_CLASSES_AR.get(value or "", value or "غير محدد")


def location_ar(value: str | None) -> str:
    return CHECKPOINT_LOCATIONS_AR.get(value or "", value or "غير محدد")


def agency_ar(value: str | None) -> str:
    return AGENCIES_AR.get(value or "", "الجهة المختصة")


def datetime_ar(iso_value: str | None) -> str:
    """'2026-09-14T11:06:29+03:00' -> '14 سبتمبر 2026، الساعة 11:06 صباحًا'."""
    if not iso_value:
        return "غير محدد"
    try:
        moment = datetime.datetime.fromisoformat(iso_value)
    except ValueError:
        return iso_value
    hour = moment.hour % 12 or 12
    period = "صباحًا" if moment.hour < 12 else "مساءً"
    return f"{moment.day} {_MONTHS_AR[moment.month - 1]} {moment.year}، الساعة {hour}:{moment.minute:02d} {period}"
