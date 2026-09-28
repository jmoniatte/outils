"""JSON from the web services the tabs ask (Open-Meteo, ipinfo.io, Wikipedia), with urllib; no Textual."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import REPOSITORY_URL, __version__

TIMEOUT = 10
# Wikipedia refuses urllib's own User-Agent, and asks for one that says who is calling
USER_AGENT = f"outils/{__version__} ({REPOSITORY_URL})"


def get_json(url: str, service: str, error: type[Exception]) -> object:
    """The JSON at url; any failure is raised as error, with a message fit to show that names the service."""
    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT) as response:
            return json.load(response)
    except HTTPError as failed:
        raise error(f"{service} answered {failed.code}") from None
    except (URLError, TimeoutError, OSError) as failed:
        raise error(f"Cannot reach {service}: {getattr(failed, 'reason', failed)}") from None
    except ValueError:
        raise error(f"{service} did not answer with JSON") from None
