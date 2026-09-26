"""Every pactl call and the parsing of its JSON output; blocking, call via asyncio.to_thread.

pactl talks to PulseAudio, or to PipeWire through pipewire-pulse, so this works on both.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace

from . import command

TIMEOUT = 5
# pavucontrol lets a slider go past 100% up to 153%; that distorts, so the keys stop here
MAX_VOLUME = 100

# Kinds, named as pactl names them in its set-<kind>-volume, set-<kind>-mute and set-default-<kind> commands
SINK = "sink"
SOURCE = "source"
# What plays on a sink and what records from a source, as pactl lists them
STREAMS = {SINK: "sink-inputs", SOURCE: "source-outputs"}

# Short names by the type of the active port; Bluetooth devices keep their own name
PORT_LABELS = {
    "Speaker": "Laptop speakers",
    "Headphones": "Headphone jack",
    "HDMI": "Monitor",
    "DisplayPort": "Monitor",
}


class PactlError(Exception):
    """pactl failed, or is missing; the message is fit to show."""


@dataclass(frozen=True, slots=True)
class Device:
    """An output (sink) or a microphone (source), or paired headphones with no sink yet.

    Bluetooth devices carry their address in `mac`; see bluetooth.merge for the rest.
    """

    kind: str
    # pactl's number for the device, for its commands only; None for headphones with no sink
    index: int | None
    name: str
    label: str
    volume: int
    muted: bool
    default: bool = False
    mac: str = ""
    # The Bluetooth link; always True for a wired device
    connected: bool = True
    battery: int | None = None

    @property
    def playable(self) -> bool:
        """Whether there is a sink or source behind it to set the volume of and switch to."""
        return self.index is not None

    @property
    def key(self) -> str:
        """Who it is across reloads: its Bluetooth address for headphones, connected or not, else pactl's name."""
        return f"{self.kind}-{self.mac or self.name}"


@dataclass(frozen=True, slots=True)
class Mixer:
    """The two sections of the screen."""

    outputs: list[Device] = field(default_factory=list)
    inputs: list[Device] = field(default_factory=list)


def run(*args: str) -> str:
    result = command.run(["pactl", *args], PactlError, TIMEOUT)
    if result.returncode != 0:
        raise PactlError(result.stderr.strip() or f"pactl {args[0]} failed")
    return result.stdout


def _json(*args: str) -> object:
    return json.loads(run("--format=json", *args) or "null")


def average_volume(volume: object) -> int:
    """The mean of the channels' percentages; pactl reports each channel as '80%'."""
    if not isinstance(volume, dict) or not volume:
        return 0
    values = [int(str(channel.get("value_percent", "0")).rstrip("%")) for channel in volume.values()]
    return round(sum(values) / len(values))


def _active_port(entry: dict) -> dict:
    return next((port for port in entry.get("ports") or [] if port.get("name") == entry.get("active_port")), {})


def is_plugged(entry: dict) -> bool:
    """A device with no ports, or whose port is not known to be unplugged; the four HDMI outputs of a video card
    are listed whether a screen is connected or not."""
    return _active_port(entry).get("availability") != "not available"


def is_monitor(entry: dict) -> bool:
    """For a source: whether it listens to a sink rather than a microphone.

    pactl reuses monitor_source here for the sink it listens to; on a sink it names that sink's monitor instead.
    """
    return bool(entry.get("monitor_source"))


def bluetooth_address(entry: dict) -> str:
    """The device's address, as bluetoothctl writes it, or "" for a wired device."""
    address = (entry.get("properties") or {}).get("api.bluez5.address", "")
    if not address and (match := re.match(r"bluez_\w+\.([0-9A-F_]{17})", entry["name"])):
        address = match.group(1).replace("_", ":")
    return address.upper()


def short_label(entry: dict) -> str:
    if entry["name"].startswith("bluez_"):
        return entry.get("description") or entry["name"]
    port = _active_port(entry)
    return PORT_LABELS.get(port.get("type", "")) or port.get("description") or entry.get("description") or entry["name"]


def parse_devices(kind: str, entries: list[dict], default_name: str) -> list[Device]:
    """The plugged-in devices, with their short labels."""
    kept = [entry for entry in entries if is_plugged(entry) and not (kind == SOURCE and is_monitor(entry))]
    devices = [
        Device(
            kind=kind,
            index=entry["index"],
            name=entry["name"],
            label=short_label(entry),
            volume=average_volume(entry.get("volume")),
            muted=bool(entry.get("mute")),
            default=entry["name"] == default_name,
            mac=bluetooth_address(entry),
        )
        for entry in kept
    ]
    # Two screens both read "Monitor"; the port tells them apart
    counts = Counter(device.label for device in devices)
    return [
        replace(device, label=f"{device.label} ({_active_port(entry).get('description', device.name)})")
        if counts[device.label] > 1
        else device
        for device, entry in zip(devices, kept)
    ]


def mixer() -> Mixer:
    info = _json("info")
    return Mixer(
        outputs=parse_devices(SINK, _json("list", "sinks"), info.get("default_sink_name", "")),
        inputs=parse_devices(SOURCE, _json("list", "sources"), info.get("default_source_name", "")),
    )


def set_volume(device: Device, percent: int) -> None:
    run(f"set-{device.kind}-volume", str(device.index), f"{percent}%")


def set_mute(device: Device, muted: bool) -> None:
    run(f"set-{device.kind}-mute", str(device.index), "1" if muted else "0")


def set_default(device: Device) -> None:
    """Make the device the default and move what is playing (or recording) onto it.

    Setting the default alone only affects streams opened afterwards.
    """
    run(f"set-default-{device.kind}", device.name)
    monitors = {entry["index"] for entry in _json("list", "sources") if is_monitor(entry)} if device.kind == SOURCE else set()
    for stream in _json("list", STREAMS[device.kind]):
        # Something recording what a sink plays (a screen recorder) keeps listening to it
        if stream.get(device.kind) in monitors:
            continue
        try:
            run(f"move-{STREAMS[device.kind][:-1]}", str(stream["index"]), device.name)
        except PactlError:
            pass  # a stream that ended meanwhile, or one that refuses to move
