"""A domain's registration from RDAP, whois's successor in JSON, through rdap.org: free, no account.

The calls block; the app runs them with asyncio.to_thread.
"""

from .web import get_json

URL = "https://rdap.org/domain/{}"
# A host name is tried as typed, then without its first label, and so on ("www.bbc.co.uk", then
# "bbc.co.uk"), at most this many times: a registry knows the domain, not the hosts under it
TRIES = 4
# The name servers stop at the last whole name that fits here, so their row stays on one line in the pop-up
NAME_SERVERS_WIDTH = 60
# What the view shows, in order
LABELS = ("Domain", "Registrar", "Registrant", "Registered", "Name servers")


class RdapError(Exception):
    """rdap.org could not be reached or did not answer; the IP rows show without the domain's."""


def names(host: str) -> list[str]:
    """The names to try for host, longest first, never a bare top-level domain."""
    labels = host.rstrip(".").lower().split(".")
    return [".".join(labels[start:]) for start in range(len(labels) - 1)][:TRIES]


def lookup(host: str) -> list[tuple[str, str]]:
    """(label, value) for the domain host is under; none when no registry knows it, or rdap.org fails."""
    try:
        ascii_host = host.encode("idna").decode()
    except UnicodeError:
        return []
    try:
        for name in names(ascii_host):
            data = get_json(URL.format(name), "rdap.org", RdapError, not_found=True)
            if isinstance(data, dict):
                return rows(data)
    except RdapError:
        pass
    return []


def _entity(data: dict, role: str) -> str:
    """The full name of the first entity with that role: "MarkMonitor Inc." for the registrar."""
    for entity in data.get("entities") or []:
        if role in (entity.get("roles") or []):
            vcard = (entity.get("vcardArray") or [None, []])[1]
            return next((str(field[3]).strip() for field in vcard if field and field[0] == "fn" and len(field) > 3), "")
    return ""


def _event(data: dict, action: str) -> str:
    """The day of the event, "1995-08-14", from its full time."""
    return next((str(event.get("eventDate", ""))[:10] for event in data.get("events") or [] if event.get("eventAction") == action), "")


def _dates(data: dict) -> str:
    """When the domain was registered and until when, on one row so a host's rows fit the pop-up:
    "2000-07-26, expires 2026-12-30"."""
    created, expires = _event(data, "registration"), _event(data, "expiration")
    return ", ".join(part for part in (created, f"expires {expires}" if expires else "") if part)


def _name_servers(data: dict) -> str:
    """As many whole names as fit NAME_SERVERS_WIDTH, then how many more: "ns1.google.com, ns2.google.com, +2 more"."""
    servers = [str(server.get("ldhName", "")).lower().rstrip(".") for server in data.get("nameservers") or []]
    shown: list[str] = []
    for server in servers:
        rest = len(servers) - len(shown) - 1
        more = f", +{rest} more" if rest else ""
        if shown and len(", ".join([*shown, server]) + more) > NAME_SERVERS_WIDTH:
            break
        shown.append(server)
    left = len(servers) - len(shown)
    return ", ".join(shown) + (f", +{left} more" if left else "")


def rows(data: dict) -> list[tuple[str, str]]:
    """(label, value) for each field the registry gave, in LABELS order."""
    values = (
        str(data.get("ldhName", "")).lower(),
        _entity(data, "registrar"),
        # Often hidden, for privacy
        _entity(data, "registrant"),
        _dates(data),
        _name_servers(data),
    )
    return [(label, value) for label, value in zip(LABELS, values) if value]
