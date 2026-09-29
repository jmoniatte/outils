"""The weather forecast from Open-Meteo (open-meteo.com): free, no account and no key.

Every call blocks; the app runs them with asyncio.to_thread.
"""

import json
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import NamedTuple
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from . import CACHE_DIR
from .web import get_json

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# Ten: the next weekend in most weeks, and what the pop-up has room for; Open-Meteo gives up to 16
DAYS = 10
# An hour with at least this chance of rain, in %, is one it is likely to rain
RAIN_LIKELY = 40
# A dry spell shorter than this, in hours, does not split a day's rain in two
DRY_SPELL = 2
# At most this many spans of rain, snow or storm a day, so a row fits the pop-up; the shortest dry
# spells are closed first
MAX_SPANS = 2
# A likely hour whose code shows no rain or snow is snow at this temperature (°C) or under, else rain
SNOW_BELOW = 1.0
# What a span that joins two kinds becomes: the one that matters most
SEVERITY = ("rain", "snow", "storm")
# The hours, 8am to 8pm, whose most common sky names a dry day: the daily code is the day's worst
# hour, so an evening of thin cloud made a sunny day "Overcast"
DAYTIME = range(8, 20)
# A dry day says when its sky is the opposite of its words ("Overcast 5pm–10pm" on a Clear day) in
# these hours, 7am to 10pm, for a span of at least SKY_SPAN hours; shorter ones are noise
SKY_HOURS = range(7, 22)
SKY_SPAN = 4
# The codes of the opposite sky: overcast hours on a clear day, clear hours on an overcast one; a
# partly cloudy day, or hour, has none
OPPOSITE_SKY = {0: ("overcast", {3}), 1: ("overcast", {3}), 3: ("clear", {0, 1})}
# Where a location, once found, is kept, so opening the pop-up costs one request, not two
CACHE_FILE = CACHE_DIR / "places.json"

METRIC = "metric"
IMPERIAL = "imperial"
UNITS = (METRIC, IMPERIAL)
# What the view writes after a wind speed; a temperature only gets °, and °C or °F beside the city
# says which
WIND_LABELS = {METRIC: "km/h", IMPERIAL: "mph"}

# WMO weather codes, as Open-Meteo returns them: (what it says, Nerd Font icon)
_CLEAR, _PARTLY, _CLOUDY, _FOG = "\U000f0599", "\U000f0595", "\U000f0590", "\U000f0591"
_RAIN, _POURING, _SNOW, _STORM = "\U000f0597", "\U000f0596", "\U000f0598", "\U000f0593"
_NIGHT = "\U000f0594"
# What each icon shows, which the view colors it by
SKIES = {
    _CLEAR: "clear", _PARTLY: "clear", _NIGHT: "clear", _CLOUDY: "cloud", _FOG: "cloud",
    _RAIN: "rain", _POURING: "rain", _SNOW: "snow", _STORM: "storm",
}
WEATHER_CODES = {
    0: ("Clear", _CLEAR),
    1: ("Mostly clear", _PARTLY),
    2: ("Partly cloudy", _PARTLY),
    3: ("Overcast", _CLOUDY),
    45: ("Fog", _FOG),
    48: ("Freezing fog", _FOG),
    51: ("Light drizzle", _RAIN),
    53: ("Drizzle", _RAIN),
    55: ("Heavy drizzle", _RAIN),
    56: ("Freezing drizzle", _RAIN),
    57: ("Freezing drizzle", _RAIN),
    61: ("Light rain", _RAIN),
    63: ("Rain", _RAIN),
    65: ("Heavy rain", _POURING),
    66: ("Freezing rain", _RAIN),
    67: ("Freezing rain", _POURING),
    71: ("Light snow", _SNOW),
    73: ("Snow", _SNOW),
    75: ("Heavy snow", _SNOW),
    77: ("Snow grains", _SNOW),
    80: ("Light showers", _RAIN),
    81: ("Showers", _RAIN),
    82: ("Heavy showers", _POURING),
    85: ("Snow showers", _SNOW),
    86: ("Heavy snow showers", _SNOW),
    95: ("Thunderstorm", _STORM),
    96: ("Thunderstorm, hail", _STORM),
    99: ("Thunderstorm, hail", _STORM),
}


class WeatherError(Exception):
    """Open-Meteo could not be reached, or did not know the place; the message says which."""


# What reading an answer, or a cache entry, of another shape than expected raises
_UNREADABLE = (AttributeError, IndexError, KeyError, TypeError, ValueError)
_UNREADABLE_MESSAGE = "Open-Meteo gave an answer outils cannot read"


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    region: str
    country: str
    latitude: float
    longitude: float
    # IANA, "America/Vancouver", for the Time tab; required, so a cache entry from before it is asked again
    timezone: str
    # ISO, "CA", for the calendar's holidays; required too
    country_code: str

    @property
    def label(self) -> str:
        return ", ".join(part for part in (self.name, self.region, self.country) if part)


@dataclass(frozen=True, slots=True)
class Current:
    # The place's local time
    time: datetime
    temperature: float
    feels_like: float
    wind: float
    code: int
    is_day: bool


@dataclass(frozen=True, slots=True)
class Day:
    day: date
    code: int
    high: float
    low: float


@dataclass(frozen=True, slots=True)
class Hour:
    # The place's local time
    time: datetime
    # None when Open-Meteo has no chance to give for that hour
    rain_chance: int | None
    code: int | None
    temperature: float | None

    @property
    def kind(self) -> str:
        """What falls in that hour, "rain", "snow" or "storm", from its code; the code follows the
        amount expected, not the chance, so a likely hour can have a dry one: then its temperature."""
        sky = SKIES[WEATHER_CODES[self.code][1]] if self.code in WEATHER_CODES else None
        if sky in SEVERITY:
            return sky
        return "snow" if self.temperature is not None and self.temperature <= SNOW_BELOW else "rain"


class Span(NamedTuple):
    """When rain, snow or a storm is likely, in hours of the day: from its first likely hour to the
    end of its last; None for a start at the start of the day (today: now) or an end at its end."""

    kind: str
    start: int | None
    end: int | None


@dataclass(frozen=True, slots=True)
class Forecast:
    """Always metric, as Open-Meteo gives it by default; `temperature` and `speed` convert."""

    place: Place
    current: Current
    days: list[Day]
    hours: list[Hour]


def describe(code: int, is_day: bool = True) -> tuple[str, str]:
    """What a WMO code says, and its icon; a clear night gets the moon."""
    text, icon = WEATHER_CODES.get(code, ("Unknown", _CLOUDY))
    return text, _NIGHT if icon == _CLEAR and not is_day else icon


def ask(url: str, params: dict) -> dict:
    """Open-Meteo's answer at url for params; a failure is a WeatherError."""
    return get_json(f"{url}?{urlencode(params)}", "Open-Meteo", WeatherError)


def _plain(text: str) -> str:
    """Lower case without accents, so Montréal matches Montreal."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


# The postal codes people put after a city in the US and Canada, which initials cannot all give:
# "OR" is Oregon, not O; "ME" is Maine
REGION_CODES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "NT": "Northwest Territories",
    "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}


def _initials(text: str) -> str:
    """"BC" for "British Columbia"; nothing for one word, whose first letter would match too much."""
    words = text.split()
    return "".join(word[0] for word in words) if len(words) > 1 else ""


def pick_place(location: str, results: list[dict]) -> Place | None:
    """The result that fits "City, Region, Country" best: the right name first, then the most qualifiers.

    Each qualifier after the city matches a region, a country or a country code, in full or by
    initials ("Hong Kong" for HK), or a US state or Canadian province by its postal code ("OR",
    "QC"). A place's own label, "Portland, Oregon, United States", finds that place again.
    """
    name, *qualifiers = (part.strip() for part in location.split(","))
    candidates = [r for r in results if _plain(r.get("name", "")) == _plain(name)] or results
    if not candidates:
        return None

    def matched(result: dict) -> int:
        fields = [result.get(key, "") for key in ("admin1", "admin2", "country", "country_code")]
        names = set().union(*({_plain(field), _plain(_initials(field))} for field in fields if field)) - {""}
        return sum(
            bool({_plain(q), _plain(_initials(q)), _plain(REGION_CODES.get(q.upper(), q))} & names)
            for q in qualifiers
            if q
        )

    # The first of the best, so Open-Meteo's own order breaks ties
    best = max(candidates, key=matched)
    return Place(best["name"], best.get("admin1", ""), best.get("country", ""), best["latitude"], best["longitude"], best.get("timezone", ""), best.get("country_code", ""))


def find_place(location: str, cache_file: Path = CACHE_FILE) -> Place:
    """The place a config's location names, looked up once and then read from the cache."""
    cache = _read_cache(cache_file)
    if location in cache:
        try:
            return Place(**cache[location])
        except TypeError:
            pass  # An entry of another shape is asked again, and replaced
    name = location.partition(",")[0].strip()
    data = ask(GEOCODING_URL, {"name": name, "count": 10, "language": "en", "format": "json"})
    try:
        place = pick_place(location, data.get("results") or [])
    except _UNREADABLE:
        raise WeatherError(_UNREADABLE_MESSAGE) from None
    if place is None:
        raise WeatherError(f"Open-Meteo does not know {location!r}")
    cache[location] = asdict(place)
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass  # A cache that cannot be written only costs a lookup next time
    return place


def _read_cache(cache_file: Path) -> dict:
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_forecast(place: Place, data: dict) -> Forecast:
    now = data["current"]
    # float() and int() also turn a missing value (null) into an error here, not when drawn
    current = Current(
        time=datetime.fromisoformat(now["time"]),
        temperature=float(now["temperature_2m"]),
        feels_like=float(now["apparent_temperature"]),
        wind=float(now["wind_speed_10m"]),
        code=int(now["weather_code"]),
        is_day=bool(now.get("is_day", 1)),
    )
    daily = data["daily"]
    days = [
        Day(
            day=date.fromisoformat(daily["time"][i]),
            code=int(daily["weather_code"][i]),
            high=float(daily["temperature_2m_max"][i]),
            low=float(daily["temperature_2m_min"][i]),
        )
        for i in range(len(daily["time"]))
    ]
    hourly = data["hourly"]
    hours = [
        Hour(
            time=datetime.fromisoformat(hourly["time"][i]),
            rain_chance=hourly["precipitation_probability"][i],
            code=hourly["weather_code"][i],
            temperature=hourly["temperature_2m"][i],
        )
        for i in range(len(hourly["time"]))
    ]
    days = [replace(day, code=_sky(day, hours)) for day in days]
    return Forecast(place, current, days, hours)


def _sky(day: Day, hours: list[Hour]) -> int:
    """The day's code: its own when it says rain, snow, fog or a storm, else the sky of most of its daytime hours, the cloudier on a tie."""
    if day.code > 3:
        return day.code
    codes = Counter(
        hour.code for hour in hours
        if hour.time.date() == day.day and hour.time.hour in DAYTIME and hour.code in (0, 1, 2, 3)
    )
    if not codes:
        return day.code
    return max(codes, key=lambda code: (codes[code], code))


def sky_spans(forecast: Forecast, index: int) -> list[Span]:
    """When the sky of the dry day at index is the opposite of its words, at most MAX_SPANS of the longest,
    in order; today counted from the hour begun."""
    day = forecast.days[index]
    if day.code not in OPPOSITE_SKY:
        return []
    kind, codes = OPPOSITE_SKY[day.code]
    begun = forecast.current.time.replace(minute=0, second=0, microsecond=0)
    spans: list[Span] = []
    for hour in forecast.hours:
        if hour.time.date() != day.day or hour.time < begun or hour.time.hour not in SKY_HOURS or hour.code not in codes:
            continue
        start = hour.time.hour
        if spans and spans[-1].end == start:
            spans[-1] = spans[-1]._replace(end=start + 1)
        else:
            spans.append(Span(kind, start, start + 1))
    long = [span for span in spans if span.end - span.start >= SKY_SPAN]
    longest = sorted(long, key=lambda span: span.end - span.start, reverse=True)[:MAX_SPANS]
    return [span for span in long if span in longest]


def temperature(celsius: float, units: str) -> float:
    return celsius * 9 / 5 + 32 if units == IMPERIAL else celsius


def speed(kmh: float, units: str) -> float:
    return kmh / 1.609344 if units == IMPERIAL else kmh


def weather_spans(forecast: Forecast, index: int) -> list[Span]:
    """When rain, snow or a storm is likely on the forecast's day at index; empty when none is likely."""
    day = forecast.days[index].day
    begun = forecast.current.time.replace(minute=0, second=0, microsecond=0)
    hours = [hour for hour in forecast.hours if hour.time.date() == day and hour.time >= begun]
    spans: list[Span] = []
    for hour in hours:
        if (hour.rain_chance or 0) < RAIN_LIKELY:
            continue
        start, kind = hour.time.hour, hour.kind
        if spans and spans[-1].kind == kind and start - spans[-1].end < DRY_SPELL:
            spans[-1] = spans[-1]._replace(end=start + 1)
        else:
            spans.append(Span(kind, start, start + 1))
    while len(spans) > MAX_SPANS:
        # The shortest dry spell between two of a kind, else the shortest of all
        gap = min(range(len(spans) - 1), key=lambda i: (spans[i].kind != spans[i + 1].kind, spans[i + 1].start - spans[i].end))
        first, second = spans[gap], spans.pop(gap + 1)
        spans[gap] = Span(max(first.kind, second.kind, key=SEVERITY.index), first.start, second.end)
    first_hour = hours[0].time.hour if hours else None
    return [Span(kind, None if start == first_hour else start, None if end == 24 else end) for kind, start, end in spans]


def forecast(location: str) -> Forecast:
    """The weather now, and for the next DAYS days, today included, with their hours' chance of rain, code and temperature, where location says."""
    place = find_place(location)
    params = {
        "latitude": place.latitude,
        "longitude": place.longitude,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "hourly": "precipitation_probability,weather_code,temperature_2m",
        "timezone": "auto",
        "forecast_days": DAYS,
    }
    data = ask(FORECAST_URL, params)
    try:
        return parse_forecast(place, data)
    except _UNREADABLE:
        raise WeatherError(_UNREADABLE_MESSAGE) from None
