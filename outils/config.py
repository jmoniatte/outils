from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from ouikit.config import read_theme
from ouikit.theme import TERMINAL_THEME

from .clocks import DEFAULT_CLOCKS, Clock, find_zone
from .months import WEEKDAY_NAMES
from .weather import METRIC, UNITS

CONFIG_DIR = Path.home() / ".config" / "outils"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    """Optional, hand-edited settings."""

    # Set with t in the app; "terminal" reads the terminal's own colours, otherwise any
    # scheme in ouikit (see ouikit.theme.list_themes()).
    theme: str = TERMINAL_THEME
    # The first column of the calendar, as calendar counts days: Monday is 0, Sunday 6
    week_start: int = 0
    # Where the weather opens on, as "City" or "City, Region or Country"; the view can look up another
    location: str = "Portland, OR"
    # metric or imperial
    units: str = METRIC
    # The clocks under the calendar, top to bottom
    clocks: list[Clock] = field(default_factory=lambda: _clocks(DEFAULT_CLOCKS))
    # Why the config file was ignored; the UI shows these
    warnings: list[str] = field(default_factory=list)


def load_config(path: Path = CONFIG_FILE) -> Config:
    """Read the config file if there is one; a missing file just means defaults."""
    config = Config()
    if not path.exists():
        return config

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        config.warnings.append(f"Config file is not valid YAML: {error}")
        return config
    if not isinstance(data, Mapping):
        config.warnings.append("Config file must contain a mapping of settings")
        return config

    config.theme, warning = read_theme(data.get("theme"))
    if warning:
        config.warnings.append(warning)
    _read_week_start(data.get("week_start"), config)
    _read_weather(data, config)
    _read_clocks(data.get("clocks"), config)
    return config


def _clocks(zones: Mapping[str, str]) -> list[Clock]:
    return [Clock(name, find_zone(zone)) for name, zone in zones.items()]


def _read_clocks(value: object, config: Config) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        config.warnings.append("clocks: must map names to time zones, such as Paris: Europe/Paris")
        return
    clocks = []
    for name, zone in value.items():
        found = find_zone(str(zone).strip())
        if found is None:
            config.warnings.append(f"clocks: '{zone}' is not a time zone, such as Europe/Paris")
        else:
            clocks.append(Clock(str(name), found))
    config.clocks = clocks


def _read_weather(data: Mapping, config: Config) -> None:
    location = data.get("location")
    if isinstance(location, str) and location.strip():
        config.location = location.strip()
    elif location is not None:
        config.warnings.append("location: must be a place name, such as Victoria, BC")
    units = data.get("units")
    if units is None:
        return
    if str(units).strip().lower() in UNITS:
        config.units = str(units).strip().lower()
    else:
        config.warnings.append(f"units: '{units}' is neither metric nor imperial, using metric")


def _read_week_start(value: object, config: Config) -> None:
    if value is None:
        return
    name = str(value).strip().lower()
    if name in WEEKDAY_NAMES:
        config.week_start = WEEKDAY_NAMES.index(name)
    else:
        config.warnings.append(f"week_start: '{value}' is not a day of the week, using monday")

