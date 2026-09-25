"""The time now in a few places, by their IANA time zone; no network."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The name shown, then its time zone, top to bottom
DEFAULT_CLOCKS = {
    "Portland": "America/Los_Angeles",
    "Chicago": "America/Chicago",
    "UTC": "UTC",
    "Strasbourg": "Europe/Paris",
}


@dataclass(frozen=True, slots=True)
class Clock:
    name: str
    zone: ZoneInfo


@dataclass(frozen=True, slots=True)
class Reading:
    name: str
    # "22:04"
    time: str
    # "-07:00"
    offset: str
    # Summer time in force
    dst: bool


def find_zone(zone: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def read(clock: Clock, now: datetime) -> Reading:
    """What clock shows at now, which must know its own time zone."""
    local = now.astimezone(clock.zone)
    offset = local.utcoffset() or timedelta()
    minutes = int(offset.total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    hours, minutes = divmod(abs(minutes), 60)
    return Reading(clock.name, f"{local:%H:%M}", f"{sign}{hours:02}:{minutes:02}", bool(local.dst()))
