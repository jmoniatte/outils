import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REPOSITORY_URL = "https://github.com/jmoniatte/outils"
# What outils keeps between runs: the places found, the best snake score
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "outils"

try:
    __version__ = version("outils")
except PackageNotFoundError:
    __version__ = "0.0.0"
