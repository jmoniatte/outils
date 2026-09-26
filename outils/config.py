from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from tui_kit.config import read_theme
from tui_kit.theme import TERMINAL_THEME

from .clocks import DEFAULT_CLOCKS, Clock, find_zone
from .months import WEEKDAY_NAMES
from .weather import METRIC, UNITS

CONFIG_FILE = Path.home() / ".config" / "outils" / "config.yaml"


@dataclass
class Config:
    """Optional settings, written by hand; the app itself writes only the theme and the units."""

    # Set with t in the app; "terminal" reads the terminal's own colours, otherwise any
    # scheme in tui-kit (see tui_kit.theme.list_themes()).
    theme: str = TERMINAL_THEME
    # The first column of the calendar, as calendar counts days: Monday is 0, Sunday 6
    week_start: int = 0
    # Where the weather opens on, as "City" or "City, Region or Country"; the view can look up another
    location: str = "Portland, OR"
    # metric or imperial
    units: str = METRIC
    # The Time tab's clocks, top to bottom
    clocks: list[Clock] = field(default_factory=lambda: _clocks(DEFAULT_CLOCKS))
    # What in the config file was left out, and why; the footer shows these
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


def save_units(units: str, path: Path = CONFIG_FILE) -> str | None:
    """Persist the units, leaving the rest of a hand-written config as it was; a warning when it cannot."""
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        updated = _with_value(text, "units", units)
        # Through a link, the file it points at (the config may live in a dotfiles repository)
        target = path.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written aside, then moved over the config, so a crash never leaves it half written
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(updated, encoding="utf-8")
        temporary.replace(target)
    except yaml.YAMLError:
        return f"units: not saved, {path} is not valid YAML"
    except (OSError, ValueError) as error:
        return f"units: not saved to {path}: {error}"
    return None


def _with_value(text: str, key: str, value: str) -> str:
    """text with key's value replaced, or key added at the end; ValueError unless the YAML reads back the same but for it."""
    root = yaml.compose(text)
    mapping = isinstance(root, yaml.MappingNode)
    # The last one, as yaml reads it when a key is given twice
    pair = next((pair for pair in reversed(root.value) if pair[0].value == key), None) if mapping else None
    if pair:
        start, end = pair[1].start_mark.index, pair[1].end_mark.index
        # A block scalar's span ends with its line breaks, which the next key needs
        old = text[start:end]
        updated = text[:start] + value + old[len(old.rstrip()):] + text[end:]
    elif root is None or (mapping and not root.flow_style):
        updated = f"{text.rstrip()}\n{key}: {value}\n" if text.strip() else f"{key}: {value}\n"
    else:
        raise ValueError("the file is not a mapping written one key per line")
    before = yaml.safe_load(text) or {}
    if yaml.safe_load(updated) != {**before, key: value}:
        raise ValueError("the file is written in a way outils cannot change safely")
    return updated


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
    name = str(units).strip().lower()
    if name in UNITS:
        config.units = name
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

