"""What ipinfo.io knows about an address, this computer's public (WAN) one by default: free, no account.

The calls block; the app runs them with asyncio.to_thread.
"""

import ipaddress
import socket

from .web import get_json

URL = "https://ipinfo.io/json"
# The same answer, for another address
ADDRESS_URL = "https://ipinfo.io/{}/json"
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
    data = get_json(url, "ipinfo.io", IpInfoError)
    if not isinstance(data, dict) or "ip" not in data:
        raise IpInfoError("ipinfo.io did not give an address")
    return data


def rows(data: dict) -> list[tuple[str, str]]:
    """(label, value) for each field ipinfo.io gave, in FIELDS order."""
    return [(label, str(data[key])) for key, label in FIELDS if data.get(key)]
