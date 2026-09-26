"""The paired Bluetooth audio devices, through bluetoothctl; blocking, call via asyncio.to_thread.

`bluetoothctl info` with no address shows only what is connected, so each paired device is
asked for by address.
"""

import re
import subprocess
from dataclasses import dataclass, replace

from ouikit import processes

from .pactl import SINK, Device, Mixer

TIMEOUT = 5
# Connecting waits for the device to answer, which takes a few seconds
CONNECT_TIMEOUT = 20
_DEVICE_LINE = re.compile(r"^Device ([0-9A-F:]{17}) (.*)$", re.MULTILINE)
_BATTERY = re.compile(r"Battery Percentage: 0x[0-9a-f]+ \((\d+)\)")


class BluetoothError(Exception):
    """bluetoothctl failed; the message is fit to show."""


@dataclass(frozen=True, slots=True)
class Headset:
    """A paired device that plays sound: headphones, a headset, a speaker."""

    mac: str
    name: str
    connected: bool
    battery: int | None = None


def run(*args: str, timeout: float = TIMEOUT) -> str:
    try:
        result = processes.run(["bluetoothctl", *args], timeout)
    except FileNotFoundError as error:
        raise BluetoothError("bluetoothctl is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise BluetoothError(f"bluetoothctl {args[0]} timed out") from error
    # bluetoothctl reports failures on stdout and often still exits 0
    if result.returncode != 0 or "Failed" in result.stdout:
        lines = [line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()]
        failed = [line for line in lines if "Failed" in line]
        raise BluetoothError((failed or lines or [f"bluetoothctl {args[0]} failed"])[-1])
    return result.stdout


def _field(info: str, name: str) -> str:
    match = re.search(rf"^\s*{name}: (.*)$", info, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_info(mac: str, info: str) -> Headset | None:
    """The device, or None when it does not play sound (a mouse, a keyboard)."""
    if not _field(info, "Icon").startswith("audio-"):
        return None
    battery = _BATTERY.search(info)
    return Headset(
        mac=mac,
        name=_field(info, "Alias") or _field(info, "Name") or mac,
        connected=_field(info, "Connected") == "yes",
        battery=int(battery.group(1)) if battery else None,
    )


def headsets() -> list[Headset]:
    """The paired audio devices; none when bluetoothctl is missing or Bluetooth is off."""
    try:
        paired = run("devices", "Paired")
    except BluetoothError:
        return []
    found = []
    for mac, _ in _DEVICE_LINE.findall(paired):
        try:
            headset = parse_info(mac, run("info", mac))
        except BluetoothError:
            continue
        if headset is not None:
            found.append(headset)
    return found


def connect(mac: str) -> None:
    run("connect", mac, timeout=CONNECT_TIMEOUT)


def disconnect(mac: str) -> None:
    run("disconnect", mac)


def merge(mixer: Mixer, found: list[Headset]) -> Mixer:
    """Add the battery to the outputs that are headsets, and a row for each headset with no sink.

    A headset has no sink while disconnected, and for a moment after it connects. Its row has
    a negative index, which Device.playable reads as nothing to set the volume of.
    """
    by_mac = {headset.mac: headset for headset in found}

    def with_battery(device: Device) -> Device:
        headset = by_mac.get(device.mac)
        return replace(device, battery=headset.battery) if headset else device

    outputs = [with_battery(device) for device in mixer.outputs]
    playing = {device.mac for device in outputs}
    missing = [headset for headset in found if headset.mac not in playing]
    outputs += [
        Device(SINK, -1 - number, f"bluez:{headset.mac}", headset.name, 0, False,
               mac=headset.mac, connected=headset.connected, battery=headset.battery)
        for number, headset in enumerate(missing)
    ]
    return Mixer(outputs=outputs, inputs=[with_battery(device) for device in mixer.inputs])
