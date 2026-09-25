"""Epoch timestamps to dates and back; no network."""

import re
from datetime import UTC, datetime, timedelta, tzinfo

# Digits and an optional fraction, either sign
NUMBER = re.compile(r"[+-]?\d+(\.\d+)?")
# Milliseconds, 13 digits and no fraction: 2001 to 2286. As seconds it would be past year 33000
MILLISECONDS = re.compile(r"[+-]?\d{13}")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# For "3 days ago": the unit and its length in seconds, largest first
SPANS = (("year", 365 * 86400), ("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1))


class EpochError(Exception):
    """What was typed is neither a timestamp nor a date; the message says so."""


def parse(text: str, now: datetime, local: tzinfo | None = None) -> datetime:
    """The moment text names: a timestamp in seconds, or milliseconds when it has 13 digits, or an
    ISO date. A date without an offset is
    local time, the system's when local is None; an empty box is now.
    """
    text = text.strip()
    if not text or text.lower() == "now":
        return now
    if NUMBER.fullmatch(text):
        value = float(text) / (1000 if MILLISECONDS.fullmatch(text) else 1)
        try:
            return datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            raise EpochError(f"{text} seconds is too far from 1970 to be a date") from None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise EpochError(f"Not a timestamp or a date such as 2026-09-24 15:30: {text}") from None
    if moment.tzinfo is None:
        # With no zone given, astimezone reads a naive time as the system's, summer time included
        return moment.replace(tzinfo=local) if local else moment.astimezone()
    return moment


def seconds(moment: datetime) -> str:
    """The timestamp in seconds, with milliseconds when it has any, cut like isoformat's."""
    total = (moment - EPOCH) // timedelta(milliseconds=1)
    whole, millis = divmod(abs(total), 1000)
    sign = "-" if total < 0 else ""
    return f"{sign}{whole}.{millis:03}".rstrip("0") if millis else f"{sign}{whole}"


def relative(moment: datetime, now: datetime) -> str:
    """How far moment is from now, in its largest unit: "3 days ago", "in 2 hours"."""
    delta = int((moment - now).total_seconds())
    if abs(delta) < 1:
        return "now"
    for name, length in SPANS:
        if abs(delta) >= length:
            count = abs(delta) // length
            words = f"{count} {name}{'s' if count > 1 else ''}"
            return f"in {words}" if delta > 0 else f"{words} ago"
    return "now"


def rows(moment: datetime, now: datetime, local: tzinfo | None = None) -> list[tuple[str, str]]:
    """(label, value) for everything the view shows about moment; local None is the system's zone."""
    # ISO 8601 both: milliseconds only when there are some
    timespec = "milliseconds" if moment.microsecond else "seconds"
    return [
        ("Seconds", seconds(moment)),
        ("UTC", moment.astimezone(UTC).isoformat(timespec=timespec)),
        ("Local", moment.astimezone(local).isoformat(timespec=timespec)),
        ("Relative", relative(moment, now)),
    ]
