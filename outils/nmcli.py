"""NetworkManager through nmcli: scan, connect, disconnect and forget Wi-Fi networks, and show the one in use.

Every call blocks until nmcli exits; the app runs them with asyncio.to_thread.
"""

from dataclasses import dataclass

from . import command

# How long nmcli waits for a connection to come up before giving up
CONNECT_TIMEOUT = 30
WIFI_TYPE = "802-11-wireless"
_SCAN_FIELDS = "IN-USE,SSID,FREQ,SIGNAL,SECURITY"


class NmcliError(Exception):
    """nmcli failed, or is not installed; the message is what it printed."""


@dataclass(frozen=True, slots=True)
class Network:
    """One SSID as the list shows it, merged from every access point that broadcasts it."""

    ssid: str
    signal: int
    security: str
    frequency: int
    in_use: bool = False
    # The saved profile for this SSID, or "" when there is none
    saved_uuid: str = ""
    # False for a saved profile whose network is not around; signal, security and band are then unknown
    in_range: bool = True

    @property
    def saved(self) -> bool:
        return bool(self.saved_uuid)

    @property
    def open(self) -> bool:
        return not self.security

    @property
    def enterprise(self) -> bool:
        """802.1X needs a user and a certificate, which a password prompt cannot collect."""
        return "802.1X" in self.security

    @property
    def band(self) -> str:
        return band_name(self.frequency)


def run(*args: str, stdin: str | None = None, timeout: float = 30) -> str:
    """Run nmcli and return its output, raising NmcliError with its message when it fails."""
    result = command.run(["nmcli", *args], NmcliError, timeout, input=stdin)
    if result.returncode != 0:
        raise NmcliError(_error_message(result.stderr or result.stdout))
    return result.stdout


def _error_message(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    message = lines[-1] if lines else "nmcli failed"
    return message.removeprefix("Error: ")


def split_terse(line: str) -> list[str]:
    """Split one line of `nmcli -t` output into its fields; terse mode escapes ':' and '\\' in a value."""
    fields, current, escaped = [], [], False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def terse_rows(output: str, width: int) -> list[list[str]]:
    """The lines of `nmcli -t` output split into their fields, leaving out any without width of them."""
    return [fields for fields in map(split_terse, output.splitlines()) if len(fields) == width]


def _rows(fields: str, *args: str) -> list[list[str]]:
    """Run nmcli in terse mode for the comma-separated fields and return its rows."""
    return terse_rows(run("-t", "-f", fields, *args), fields.count(",") + 1)


def parse_scan(output: str, saved: dict[str, str]) -> list[Network]:
    """One Network per SSID, the one in use first, then by signal.

    A merged row takes its signal and band from the access point in use, else the strongest.
    Hidden networks (no SSID) are left out.
    """
    best: dict[str, Network] = {}
    for in_use, ssid, frequency, signal, security in terse_rows(output, 5):
        if not ssid:
            continue
        network = Network(
            ssid=ssid,
            signal=_number(signal),
            security=_security(security),
            frequency=_number(frequency),
            in_use=in_use.strip() == "*",
            saved_uuid=saved.get(ssid, ""),
        )
        current = best.get(ssid)
        if current is None or _better(network, current):
            best[ssid] = network
    return sorted(best.values(), key=lambda network: (not network.in_use, -network.signal, network.ssid.lower()))


def _better(candidate: Network, current: Network) -> bool:
    if candidate.in_use != current.in_use:
        return candidate.in_use
    return candidate.signal > current.signal


def _number(text: str) -> int:
    """The number a value starts with ("2437 MHz", "130 Mbit/s"), or 0 when there is none."""
    words = text.split()
    return int(words[0]) if words and words[0].isdigit() else 0


def _security(text: str) -> str:
    """nmcli writes "--" for an open network; "" here."""
    return "" if text == "--" else text


def saved_networks() -> dict[str, str]:
    """SSID -> UUID of every saved Wi-Fi profile; a profile's name need not be its SSID."""
    uuids = [uuid for uuid, kind in _rows("UUID,TYPE", "connection", "show") if kind == WIFI_TYPE]
    if not uuids:
        return {}
    output = run("-t", "-f", "connection.uuid,802-11-wireless.ssid", "connection", "show", *uuids)
    return parse_profiles(output)


def parse_profiles(output: str) -> dict[str, str]:
    """Read `connection show` of several profiles: blocks of field:value lines, one block per profile."""
    ssids: dict[str, str] = {}
    uuid = ""
    for line in output.splitlines():
        key, _, value = line.partition(":")
        if key == "connection.uuid":
            uuid = value
        elif key == "802-11-wireless.ssid" and uuid and value:
            ssids.setdefault(value, uuid)
    return ssids


def saved_list(nearby: list[Network], saved: dict[str, str]) -> list[Network]:
    """Every saved profile: the ones in range as the scan saw them, then the others by name."""
    in_range = [network for network in nearby if network.saved]
    seen = {network.ssid for network in in_range}
    away = [
        Network(ssid, signal=0, security="", frequency=0, saved_uuid=uuid, in_range=False)
        for ssid, uuid in sorted(saved.items(), key=lambda item: item[0].lower())
        if ssid not in seen
    ]
    return in_range + away


def wifi_enabled() -> bool:
    return run("radio", "wifi").strip() == "enabled"


def set_wifi(on: bool) -> None:
    run("radio", "wifi", "on" if on else "off")


def connectivity() -> str:
    """NetworkManager's last check: full, limited (no internet), portal (a login page first), none or unknown."""
    return run("-t", "networking", "connectivity").strip()


@dataclass(frozen=True, slots=True)
class Scan:
    """What the two tabs show."""

    nearby: list[Network]
    saved: list[Network]


def scan(rescan: bool = False) -> Scan:
    """The networks in range and the saved profiles; rescan asks the card to look again instead of reusing its last results."""
    output = run(
        "-t", "-f", _SCAN_FIELDS, "device", "wifi", "list", "--rescan", "yes" if rescan else "no", timeout=60
    )
    saved = saved_networks()
    nearby = parse_scan(output, saved)
    return Scan(nearby, saved_list(nearby, saved))


def connect(network: Network, password: str = "") -> None:
    """Join a network: through its saved profile, or with the password, which nmcli reads on stdin.

    The password never goes on the command line, where `ps` would show it. When the password is
    wrong, the profile nmcli created for it is deleted so the next try asks again.
    """
    wait = str(CONNECT_TIMEOUT)
    if network.saved:
        run("--wait", wait, "connection", "up", "uuid", network.saved_uuid, timeout=CONNECT_TIMEOUT + 10)
        return
    try:
        run(
            "--ask", "--wait", wait, "device", "wifi", "connect", network.ssid,
            stdin=f"{password}\n", timeout=CONNECT_TIMEOUT + 10,
        )
    except NmcliError:
        _forget_new_profile(network.ssid)
        raise


def _forget_new_profile(ssid: str) -> None:
    try:
        uuid = saved_networks().get(ssid)
        if uuid:
            run("connection", "delete", "uuid", uuid)
    except NmcliError:
        pass  # The connect error is the one worth showing


def disconnect() -> str:
    """Take down the active Wi-Fi connection; returns its name, or "" when there was none."""
    for name, uuid, kind in _rows("NAME,UUID,TYPE", "connection", "show", "--active"):
        if kind == WIFI_TYPE:
            run("connection", "down", "uuid", uuid)
            return name
    return ""


def forget(network: Network) -> None:
    """Delete the saved profile, so the next connect asks for the password again."""
    run("connection", "delete", "uuid", network.saved_uuid)


@dataclass(frozen=True, slots=True)
class Details:
    """The Wi-Fi connection in use, as the details panel shows it."""

    device: str
    ssid: str
    # The profile in use, which the Share tab reads the password from
    uuid: str = ""
    security: str = ""
    frequency: int = 0
    channel: int = 0
    signal: int = 0
    # Mbit/s; 0 when the driver does not report it
    rate: int = 0
    bssid: str = ""
    mac: str = ""
    addresses: tuple[str, ...] = ()
    gateway: str = ""
    dns: tuple[str, ...] = ()
    ipv6: tuple[str, ...] = ()

    @property
    def band(self) -> str:
        return band_name(self.frequency)


def band_name(frequency: int) -> str:
    if frequency >= 5925:
        return "6 GHz"
    if frequency >= 5000:
        return "5 GHz"
    return "2.4 GHz"


def wifi_device() -> str:
    """The Wi-Fi device that is connected, or "" when none is."""
    for device, kind, state in _rows("DEVICE,TYPE,STATE", "device"):
        if kind == "wifi" and state == "connected":
            return device
    return ""


def details() -> Details | None:
    """The connection in use and its addresses, or None when Wi-Fi is not connected."""
    device = wifi_device()
    if not device:
        return None
    shown = run(
        "-t", "-f", "GENERAL.CONNECTION,GENERAL.CON-UUID,GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS,IP6.ADDRESS",
        "device", "show", device,
    )
    access_points = run(
        "-t", "-f", "IN-USE,BSSID,SSID,CHAN,FREQ,RATE,SIGNAL,SECURITY",
        "device", "wifi", "list", "ifname", device, "--rescan", "no",
    )
    return parse_details(device, shown, access_points)


def parse_details(device: str, shown: str, access_points: str) -> Details:
    """Combine `device show` (field:value lines, lists as FIELD[n]) with the access point in use from `wifi list`."""
    values: dict[str, list[str]] = {}
    for line in shown.splitlines():
        key, _, value = line.partition(":")
        if value:
            values.setdefault(key.split("[")[0], []).append(value)
    first = {key: found[0] for key, found in values.items()}
    # Blank when the access point in use is not listed: Details' defaults
    _, bssid, ssid, channel, frequency, rate, signal, security = next(
        (fields for fields in terse_rows(access_points, 8) if fields[0] == "*"), [""] * 8
    )
    return Details(
        device=device,
        ssid=ssid or first.get("GENERAL.CONNECTION", ""),
        uuid=first.get("GENERAL.CON-UUID", ""),
        security=_security(security),
        frequency=_number(frequency),
        channel=_number(channel),
        signal=_number(signal),
        rate=_number(rate),
        bssid=bssid,
        mac=first.get("GENERAL.HWADDR", ""),
        addresses=tuple(values.get("IP4.ADDRESS", ())),
        gateway=first.get("IP4.GATEWAY", ""),
        dns=tuple(values.get("IP4.DNS", ())),
        ipv6=tuple(values.get("IP6.ADDRESS", ())),
    )


_SECRET_FIELDS = (
    "802-11-wireless.ssid,802-11-wireless-security.key-mgmt,"
    "802-11-wireless-security.psk,802-11-wireless-security.wep-key0"
)


@dataclass(frozen=True, slots=True)
class Share:
    """What someone needs to join a saved network: its name, security and password."""

    ssid: str
    # NetworkManager's key-mgmt: wpa-psk, sae, none (WEP), wpa-eap..., or "" for an open network
    key_mgmt: str
    password: str

    @property
    def enterprise(self) -> bool:
        return self.key_mgmt.startswith("wpa-eap") or self.key_mgmt == "ieee8021x"

    @property
    def qr_security(self) -> str | None:
        """The T: field of the WIFI: text phones read; WPA also covers WPA3 (sae)."""
        if not self.key_mgmt:
            return None
        return "WEP" if self.key_mgmt == "none" else "WPA"


def share(uuid: str) -> Share:
    """Read a saved profile's password; -s asks NetworkManager for the secrets, which it gives the owner of the session."""
    return parse_share(run("-s", "-t", "-f", _SECRET_FIELDS, "connection", "show", "uuid", uuid))


def parse_share(output: str) -> Share:
    """Read field:value lines; with -t -f, nmcli does not escape the values, so the first ':' splits."""
    fields = {}
    for line in output.splitlines():
        key, _, value = line.partition(":")
        fields[key] = value
    return Share(
        ssid=fields.get("802-11-wireless.ssid", ""),
        key_mgmt=fields.get("802-11-wireless-security.key-mgmt", ""),
        password=fields.get("802-11-wireless-security.psk") or fields.get("802-11-wireless-security.wep-key0", ""),
    )
