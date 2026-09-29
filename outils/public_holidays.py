"""The public holidays of a place's country, and of its state or province in the US and Canada,
through the holidays package; no Textual."""

from datetime import date
from functools import cache

import holidays

from .weather import REGION_CODES, Place

# Only these have their regions in REGION_CODES, by postal code, as the holidays package names them
REGION_COUNTRIES = ("US", "CA")
# Regions whose language is not their country's, as the holidays package has it: Canada's is English
REGION_LANGUAGES = {("CA", "QC"): "fr"}


@cache
def _calendar(country: str, region: str, year: int) -> holidays.HolidayBase | None:
    """The country's holidays that year, with its region's when the package has them, named in the
    place's own language: "Fête nationale" in France; None for a country it does not have."""
    if country not in holidays.list_supported_countries():
        return None
    subdiv = region if region in holidays.list_supported_countries()[country] else None
    # Named, not left to the package, which would follow the system's locale
    language = REGION_LANGUAGES.get((country, region)) or holidays.country_holidays(country).default_language
    return holidays.country_holidays(country, subdiv=subdiv, years=year, language=language)


def region_code(place: Place) -> str:
    """ "OR" for a place in Oregon; nothing outside the US and Canada."""
    if place.country_code not in REGION_COUNTRIES:
        return ""
    return next((code for code, name in REGION_CODES.items() if name == place.region), "")


def on(day: date, place: Place | None) -> list[str]:
    """The names of the public holidays on day where place is; none without a place."""
    calendar = place and _calendar(place.country_code, region_code(place), day.year)
    return calendar.get_list(day) if calendar else []
