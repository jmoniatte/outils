import asyncio
from dataclasses import replace
from functools import partial

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from tui_kit.shortcuts import GENERAL

from .. import bluetooth, pactl, status_bar
from ..bluetooth import BluetoothError
from ..config import Config
from ..pactl import MAX_VOLUME, Device, Mixer, PactlError
from ..reload import Reload
from .device_card import (
    BluetoothRequested,
    DefaultRequested,
    DeviceCard,
    MuteRequested,
    VolumeRequested,
    card_id,
)

# Mixer's fields, in screen order; a line separates them rather than a title
SECTIONS = ("outputs", "inputs")
# Picks up what changed elsewhere: headphones connected, a volume set by another program
REFRESH_SECONDS = 2
# How long to wait for the sink of headphones that just connected
SINK_WAIT_SECONDS = 10
SINK_POLL_SECONDS = 0.5


class SoundView(Vertical):
    """The outputs and the microphones plugged in, through pactl, one card each: which one is in
    use, and its volume and mute. Headphones paired over Bluetooth get a card too, to connect them.

    It asks pactl only while its tab shows.
    """

    BINDINGS = [
        Binding("down", "move(1)", "Next / previous device", key_display="↓ ↑", group=GENERAL),
        Binding("up", "move(-1)", show=False),
        Binding("j", "move(1)", show=False),
        Binding("k", "move(-1)", show=False),
    ]
    # The keys of the card in focus, then the view's own
    HELP_BINDINGS = (DeviceCard.BINDINGS, BINDINGS)

    def __init__(self, config: Config) -> None:
        super().__init__(id="sound")
        # pactl calls run one at a time, so fast key repeats land in the order they were pressed
        self._pactl_lock = asyncio.Lock()
        # The headphones being connected or disconnected, whose card says so; one at a time
        self.bluetooth_busy: Device | None = None
        # The last pactl failure while reloading, so it is shown once
        self._load_error: str | None = None
        # A card takes focus only while the tab shows: TabbedContent would switch to a hidden one
        self.showing = False
        self._reload = Reload(self._load_mixer)

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="sound-sections"):
            for section_id in SECTIONS:
                yield Vertical(id=f"{section_id}-cards", classes="section-cards")

    def on_mount(self) -> None:
        self.timer = self.set_interval(REFRESH_SECONDS, partial(self.load_mixer, tick=True), pause=True)

    def tab_shown(self) -> None:
        """The tab shows: focus on the output in use, and ask pactl until it hides."""
        self.showing = True
        self._focus_card()
        self.load_mixer()
        self.timer.resume()

    def tab_hidden(self) -> None:
        self.showing = False
        self.timer.pause()

    # -- the cards

    def cards(self, section_id: str | None = None) -> list[DeviceCard]:
        """The cards on show, top to bottom, of one section or of both."""
        sections = [section_id] if section_id else SECTIONS
        return [card for section in sections for card in self.query_one(f"#{section}-cards").query(DeviceCard)]

    def _focus_card(self, wanted_id: str | None = None) -> None:
        """Focus on the card with that id, else on the output in use, else on the first card."""
        cards = self.cards()
        in_use = [card for card in self.cards("outputs") if card.device.default]
        if target := next((card for card in cards if card.id == wanted_id), None) or next(iter(in_use + cards), None):
            target.focus()

    def _is_busy(self, device: Device) -> bool:
        return self.bluetooth_busy is not None and device.mac == self.bluetooth_busy.mac

    async def show(self, mixer: Mixer) -> None:
        focused = self.screen.focused
        focused_id = focused.id if isinstance(focused, DeviceCard) else None
        for section_id in SECTIONS:
            devices: list[Device] = getattr(mixer, section_id)
            container = self.query_one(f"#{section_id}-cards")
            cards = list(container.query(DeviceCard))
            if [card.id for card in cards] == [card_id(device) for device in devices]:
                # Same devices: update in place, so focus stays where it is
                for card, device in zip(cards, devices):
                    card.update(device, busy=self._is_busy(device))
            else:
                await container.remove_children()
                await container.mount_all(DeviceCard(device, busy=self._is_busy(device)) for device in devices)
            # No microphone plugged in, as on a desktop without a headset: drop the section and its line
            container.display = bool(devices)
        every_device = (*mixer.outputs, *mixer.inputs)
        has_headphones = any(device.mac for device in every_device)
        # Every name whole: the name column is never narrower than the longest one
        longest = max((len(device.label) for device in every_device), default=0)
        for card in self.cards():
            card.set_columns(longest, has_headphones)
        if self.showing and not isinstance(self.screen.focused, DeviceCard):
            # Back on the device that had focus once its section was remounted; on first load, on the output in use
            self._focus_card(focused_id)

    def redraw(self, device: Device) -> None:
        """Redraw one device with new values, before pactl has confirmed them."""
        for card in self.cards():
            if card.id == card_id(device):
                card.update(device)

    def _show_busy(self) -> None:
        for card in self.cards():
            card.update(card.device, busy=self._is_busy(card.device))

    def action_move(self, step: int) -> None:
        """Up and down go through both sections as one list."""
        cards = self.cards()
        if not cards:
            return
        focused = self.screen.focused
        index = cards.index(focused) if focused in cards else -step
        target = cards[max(0, min(len(cards) - 1, index + step))]
        target.focus()

    # -- pactl and bluetoothctl

    @work(group="sound-load")
    async def load_mixer(self, tick: bool = False) -> None:
        await self._reload.run(tick)

    async def _load_mixer(self) -> None:
        try:
            mixer = await self._mixer()
        except PactlError as error:
            # Said once, not on every reload, while pactl keeps failing
            if str(error) != self._load_error:
                self.app.notify(str(error), severity="error", timeout=10)
            self._load_error = str(error)
            return
        self._load_error = None
        headsets = await asyncio.to_thread(bluetooth.headsets)
        # Not shown when a change came in meanwhile: it would undo the change on screen until the next reload
        if not self._reload.overtaken:
            await self.show(bluetooth.merge(mixer, headsets))

    async def _mixer(self) -> Mixer:
        async with self._pactl_lock:
            return await asyncio.to_thread(pactl.mixer)

    @on(VolumeRequested)
    def _volume_requested(self, event: VolumeRequested) -> None:
        event.stop()
        device = event.device
        volume = max(0, min(MAX_VOLUME, event.volume))
        if volume == device.volume:
            return
        # Shown at once, so holding the key does not wait on pactl
        self.redraw(replace(device, volume=volume))
        self._change(pactl.set_volume, device, volume)

    @on(MuteRequested)
    def _mute_requested(self, event: MuteRequested) -> None:
        event.stop()
        device = event.device
        self.redraw(replace(device, muted=not device.muted))
        self._change(pactl.set_mute, device, not device.muted)

    @on(DefaultRequested)
    def _default_requested(self, event: DefaultRequested) -> None:
        event.stop()
        device = event.device
        verb = "Playing on" if device.kind == pactl.SINK else "Recording from"
        self._change(pactl.set_default, device, message=f"{verb} {device.label}")

    @on(BluetoothRequested)
    def _bluetooth_requested(self, event: BluetoothRequested) -> None:
        event.stop()
        if self.bluetooth_busy is not None:
            self.app.notify(f"Still busy with {self.bluetooth_busy.label}", severity="warning")
            return
        self._bluetooth(event.device, event.use)

    @work(group="sound-bluetooth")
    async def _bluetooth(self, device: Device, use: bool) -> None:
        """Connect or disconnect headphones; with `use`, switch to them once their sink shows up."""
        self.bluetooth_busy = device
        self._show_busy()
        # Stays up until the outcome replaces it
        verb = "Disconnecting from" if device.connected else "Connecting to"
        self.app.notify(f"{verb} {device.label}...", timeout=bluetooth.CONNECT_TIMEOUT + SINK_WAIT_SECONDS)
        try:
            if device.connected:
                await asyncio.to_thread(bluetooth.disconnect, device.mac)
                self.app.notify(f"Disconnected from {device.label}")
            else:
                await asyncio.to_thread(bluetooth.connect, device.mac)
                self.app.notify(f"Connected to {device.label}")
                if use and (sink := await self._wait_for_sink(device.mac)) is not None:
                    await asyncio.to_thread(pactl.set_default, sink)
                    self.app.notify(f"Playing on {sink.label}")
            await asyncio.to_thread(status_bar.refresh)
        except (BluetoothError, PactlError) as error:
            self.app.notify(f"{device.label}: {error}", severity="error", timeout=10)
        finally:
            self.bluetooth_busy = None
            self._show_busy()
        self.load_mixer()

    async def _wait_for_sink(self, mac: str) -> Device | None:
        """The sink of headphones that just connected; PipeWire takes a moment to make it."""
        for _ in range(int(SINK_WAIT_SECONDS / SINK_POLL_SECONDS)):
            mixer = await self._mixer()
            if sink := next((device for device in mixer.outputs if device.mac == mac), None):
                return sink
            await asyncio.sleep(SINK_POLL_SECONDS)
        self.app.notify("Connected, but no sound output showed up for it", severity="warning")
        return None

    @work(group="sound-change")
    async def _change(self, call, *args, message: str = "") -> None:
        try:
            async with self._pactl_lock:
                await asyncio.to_thread(call, *args)
        except PactlError as error:
            self.app.notify(str(error), severity="error")
        else:
            if message:
                self.app.notify(message)
            await asyncio.to_thread(status_bar.refresh)
        self.load_mixer()
