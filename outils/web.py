"""JSON from the web services the tabs ask (Open-Meteo, ipinfo.io, rdap.org), with urllib; no Textual."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import REPOSITORY_URL, __version__

TIMEOUT = 10
# Say who is calling, as web services ask, rather than urllib's own User-Agent
USER_AGENT = f"outils/{__version__} ({REPOSITORY_URL})"


def get_json(url: str, service: str, error: type[Exception], not_found: bool = False) -> object:
    """The JSON at url; any failure is raised as error, with a message fit to show that names the service.

    With not_found, a 404 is None rather than a failure: the service knows nothing about it.
    """
    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT) as response:
            return json.load(response)
    except HTTPError as failed:
        if not_found and failed.code == 404:
            return None
        raise error(f"{service} answered {failed.code}") from None
    except (URLError, TimeoutError, OSError) as failed:
        raise error(f"Cannot reach {service}: {getattr(failed, 'reason', failed)}") from None
    except ValueError:
        raise error(f"{service} did not answer with JSON") from None
