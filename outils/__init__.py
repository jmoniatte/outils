from importlib.metadata import version, PackageNotFoundError

REPOSITORY_URL = "https://github.com/jmoniatte/outils"

try:
    __version__ = version("outils")
except PackageNotFoundError:
    __version__ = "0.0.0"
