"""The time now in a few places, by their IANA time zone; no network."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

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
    # IANA, "America/Los_Angeles"
    zone: str


def find_zone(zone: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        return None


@cache
def _zone_keys() -> dict[str, str]:
    return {key.casefold(): key for key in available_timezones()}


# The areas of today's zone names; the rest are old aliases ("US/Pacific") or offsets ("Etc/GMT+5")
AREAS = ("Africa", "America", "Antarctica", "Arctic", "Asia", "Atlantic", "Australia", "Europe", "Indian", "Pacific")


@cache
def suggested_zones() -> list[str]:
    """The zone names worth suggesting, UTC first, then "Area/City" in order."""
    return ["UTC", *sorted(key for key in available_timezones() if key.split("/")[0] in AREAS)]


def zone_named(text: str) -> Clock | None:
    """A clock for the IANA time zone text names, case ignored ("Europe/Paris", "utc"), named after
    its last part ("Paris", "Los Angeles"); None when text names none, such as a city."""
    key = _zone_keys().get(text.strip().casefold())
    if key is None:
        return None
    return Clock(key.rsplit("/", 1)[-1].replace("_", " "), ZoneInfo(key))


def read(clock: Clock, now: datetime) -> Reading:
    """What clock shows at now, which must know its own time zone."""
    local = now.astimezone(clock.zone)
    offset = local.utcoffset() or timedelta()
    minutes = int(offset.total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    hours, minutes = divmod(abs(minutes), 60)
    return Reading(clock.name, f"{local:%H:%M}", f"{sign}{hours:02}:{minutes:02}", bool(local.dst()), clock.zone.key)

