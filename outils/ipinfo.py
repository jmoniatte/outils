"""What ipinfo.io knows about an address, this computer's public (WAN) one by default: free, no account.

The calls block; the app runs them with asyncio.to_thread.
"""

import ipaddress
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

URL = "https://ipinfo.io/json"
# The same answer, for another address
ADDRESS_URL = "https://ipinfo.io/{}/json"
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


def resolve(target: str) -> str:
    """The address target names: itself when it is one, else what the host name points to.

    A private or reserved address is refused here: ipinfo.io knows nothing about it.
    """
    try:
        address = ipaddress.ip_address(target)
    except ValueError:
        try:
            # The final dot keeps the name as typed: a search domain with a wildcard would answer for any name
            address = ipaddress.ip_address(socket.getaddrinfo(target.rstrip(".") + ".", None)[0][4][0])
        except (OSError, UnicodeError):
            raise IpInfoError(f"Not an IP address or a known host name: {target}") from None
    if not address.is_global:
        raise IpInfoError(f"{address} is a private address: nothing to look up")
    return str(address)


def fetch(target: str = "") -> dict[str, str]:
    """ipinfo.io's answer about target, an address or a host name; this computer's when empty."""
    url = ADDRESS_URL.format(resolve(target)) if target else URL
    try:
        with urlopen(url, timeout=TIMEOUT) as response:
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
