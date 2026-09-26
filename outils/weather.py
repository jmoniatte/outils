"""The weather forecast from Open-Meteo (open-meteo.com): free, no account and no key.

Every call blocks; the app runs them with asyncio.to_thread.
"""

import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from . import CACHE_DIR
from .web import get_json

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAYS = 7
# Where a location, once found, is kept, so opening the pop-up costs one request, not two
CACHE_FILE = CACHE_DIR / "places.json"

METRIC = "metric"
IMPERIAL = "imperial"
UNITS = (METRIC, IMPERIAL)
# What Open-Meteo is asked for, and what the view writes after each number
_UNIT_PARAMS = {
    METRIC: {},
    IMPERIAL: {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"},
}
UNIT_LABELS = {
    METRIC: {"temperature": "°C", "wind": "km/h", "precipitation": "mm"},
    IMPERIAL: {"temperature": "°F", "wind": "mph", "precipitation": "in"},
}

# WMO weather codes, as Open-Meteo returns them: (what it says, Nerd Font icon)
_CLEAR, _PARTLY, _CLOUDY, _FOG = "\U000f0599", "\U000f0595", "\U000f0590", "\U000f0591"
_RAIN, _POURING, _SNOW, _STORM = "\U000f0597", "\U000f0596", "\U000f0598", "\U000f0593"
_NIGHT = "\U000f0594"
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

    @property
    def label(self) -> str:
        return ", ".join(part for part in (self.name, self.region, self.country) if part)


@dataclass(frozen=True, slots=True)
class Current:
    temperature: float
    feels_like: float
    humidity: int
    precipitation: float
    wind: float
    code: int
    is_day: bool


@dataclass(frozen=True, slots=True)
class Day:
    day: date
    code: int
    high: float
    low: float
    # None when Open-Meteo has no chance to give for that day
    rain_chance: int | None
    precipitation: float


@dataclass(frozen=True, slots=True)
class Forecast:
    place: Place
    units: str
    current: Current
    days: list[Day]


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
    return Place(best["name"], best.get("admin1", ""), best.get("country", ""), best["latitude"], best["longitude"])


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


def parse_forecast(place: Place, units: str, data: dict) -> Forecast:
    now = data["current"]
    # float() and int() also turn a missing value (null) into an error here, not when drawn
    current = Current(
        temperature=float(now["temperature_2m"]),
        feels_like=float(now["apparent_temperature"]),
        humidity=int(now["relative_humidity_2m"]),
        precipitation=float(now["precipitation"]),
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
            rain_chance=daily["precipitation_probability_max"][i],
            precipitation=float(daily["precipitation_sum"][i]),
        )
        for i in range(len(daily["time"]))
    ]
    return Forecast(place, units, current, days)


def forecast(location: str, units: str = METRIC) -> Forecast:
    """The weather now and for the next DAYS days, today included, where location says."""
    place = find_place(location)
    params = {
        "latitude": place.latitude,
        "longitude": place.longitude,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
        "timezone": "auto",
        "forecast_days": DAYS,
        **_UNIT_PARAMS[units],
    }
    data = ask(FORECAST_URL, params)
    try:
        return parse_forecast(place, units, data)
    except _UNREADABLE:
        raise WeatherError(_UNREADABLE_MESSAGE) from None
