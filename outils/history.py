"""Wikipedia's "On this day": what happened on a day of the year, in past years; no Textual."""

from dataclasses import dataclass

from .web import get_json

# The events Wikipedia's editors picked for the day, fewer and better known than the full list
URL = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected/{:02}/{:02}"


class HistoryError(Exception):
    """Wikipedia could not be reached or did not answer; the message says which."""


@dataclass(frozen=True)
class Event:
    year: int
    text: str


def events(month: int, day: int) -> list[Event]:
    """What happened on that day of the year, any year; the call blocks."""
    data = get_json(URL.format(month, day), "Wikipedia", HistoryError)
    try:
        found = [Event(int(item["year"]), item["text"].strip()) for item in data["selected"]]
    except (TypeError, KeyError, ValueError, AttributeError):
        raise HistoryError("Wikipedia did not give the day's events") from None
    if not found:
        raise HistoryError("Wikipedia has nothing for that day")
    return found
