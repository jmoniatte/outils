"""This computer's public (WAN) address and what ipinfo.io knows about it: free, no account.

The call blocks; the app runs it with asyncio.to_thread.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

URL = "https://ipinfo.io/json"
TIMEOUT = 10
# What the view shows, in order: (ipinfo's key, the label). The rest, like readme, is left out
FIELDS = (
    ("ip", "IP"),
    ("hostname", "Hostname"),
    ("city", "City"),
    ("region", "Region"),
    ("country", "Country"),
    ("postal", "Postal code"),
    ("loc", "Location"),
    ("timezone", "Time zone"),
    ("org", "Network"),
)


class IpInfoError(Exception):
    """ipinfo.io could not be reached or did not answer; the message says which."""


def fetch() -> dict[str, str]:
    """ipinfo.io's answer, as it gives it."""
    try:
        with urlopen(URL, timeout=TIMEOUT) as response:
            data = json.load(response)
    except HTTPError as error:
        raise IpInfoError(f"ipinfo.io answered {error.code}") from None
    except (URLError, TimeoutError, OSError) as error:
        raise IpInfoError(f"Cannot reach ipinfo.io: {getattr(error, 'reason', error)}") from None
    except ValueError:
        raise IpInfoError("ipinfo.io did not answer with JSON") from None
    if not isinstance(data, dict) or "ip" not in data:
        raise IpInfoError("ipinfo.io did not give an address")
    return data


def rows(data: dict) -> list[tuple[str, str]]:
    """(label, value) for each field ipinfo.io gave, in FIELDS order."""
    return [(label, str(data[key])) for key, label in FIELDS if data.get(key)]
