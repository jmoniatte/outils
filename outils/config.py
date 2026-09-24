from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from ouikit.config import read_theme
from ouikit.theme import TERMINAL_THEME

CONFIG_DIR = Path.home() / ".config" / "outils"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    """Optional, hand-edited settings."""

    # Set with t in the app; "terminal" reads the terminal's own colours, otherwise any
    # scheme in ouikit (see ouikit.theme.list_themes()).
    theme: str = TERMINAL_THEME
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
    return config

