"""One device as a row: its name, its volume and its buttons, all on one line."""

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from ..pactl import MAX_VOLUME, Device
from ouikit.shortcuts import ACTIONS

# Every volume set here is a multiple of this
VOLUME_STEP = 5
BAR = "━"
# What the highlight covers besides the bar; a click there uses the device
HIGHLIGHTED = ("card-label", "card-name", "card-battery", "card-volume", "card-state")


def step_volume(volume: int, step: int) -> int:
    """The next multiple of VOLUME_STEP up (step > 0) or down, so 61% goes to 65% or 60%."""
    if step > 0:
        return (volume // VOLUME_STEP + 1) * VOLUME_STEP
    return (volume - 1) // VOLUME_STEP * VOLUME_STEP


class VolumeRequested(Message):
    """The user asked to set a device's volume, a multiple of VOLUME_STEP."""

    def __init__(self, device: Device, volume: int) -> None:
        super().__init__()
        self.device = device
        self.volume = volume


class MuteRequested(Message):
    """The user asked to mute or unmute a device."""

    def __init__(self, device: Device) -> None:
        super().__init__()
        self.device = device


class DefaultRequested(Message):
    """The user asked to use a device: make it the default and move what plays on it."""

    def __init__(self, device: Device) -> None:
        super().__init__()
        self.device = device


class BluetoothRequested(Message):
    """The user asked to connect or disconnect headphones; with `use`, to switch to them once connected."""

    def __init__(self, device: Device, use: bool = False) -> None:
        super().__init__()
        self.device = device
        self.use = use


# Nerd Font (Material Design) battery icons: empty, then 10% to 90%, then full. A terminal without a
# Nerd Font shows a box; the percentage after it still says it all
BATTERY_ICONS = ("\U000f008e", *(chr(0xF007A + step) for step in range(9)), "\U000f0079")


def battery_text(level: int) -> str:
    """The icon for the level, rounded down to the tens, then the percentage: 󰁽 45%."""
    return f"{BATTERY_ICONS[max(0, min(10, level // 10))]} {level}%"


def card_id(device: Device) -> str:
    return f"device-{device.kind}-{device.index}"


class VolumeBar(Widget):
    """The volume as a bar as wide as the space it gets; a click sets the volume at that point."""

    COMPONENT_CLASSES = {"volume-bar--lit", "volume-bar--unlit"}

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.volume = 0

    def set_volume(self, volume: int) -> None:
        self.volume = volume
        self.refresh()

    def render(self) -> Text:
        width = self.content_size.width
        lit = round(width * min(self.volume, MAX_VOLUME) / MAX_VOLUME)
        text = Text(BAR * lit, style=self.get_component_rich_style("volume-bar--lit"))
        text.append(BAR * (width - lit), style=self.get_component_rich_style("volume-bar--unlit"))
        return text

    def volume_at(self, x: int) -> int:
        """The volume a click at column `x` asks for, to the nearest VOLUME_STEP; the last column is 100%."""
        width = max(self.content_size.width, 1)
        volume = max(0, min(width, x + 1)) * MAX_VOLUME / width
        return round(volume / VOLUME_STEP) * VOLUME_STEP


class DeviceCard(Horizontal, can_focus=True):
    """A device on one line: the name (green when in use) and battery, the volume figure and bar, Mute, and the
    Bluetooth button.

    Every action on a device sits on its row, so nothing depends on which row has focus.
    """

    BINDINGS = [
        Binding("left", "volume(-1)", "Volume down", key_display="←", group=ACTIONS),
        Binding("right", "volume(1)", "Volume up", key_display="→", group=ACTIONS),
        Binding("h", "volume(-1)", show=False),
        Binding("l", "volume(1)", show=False),
        Binding("m", "mute", "Mute / unmute", group=ACTIONS),
        Binding("enter", "use", "Use this device", group=ACTIONS),
        Binding("c", "bluetooth", "Connect / disconnect", group=ACTIONS),
    ]

    def __init__(self, device: Device) -> None:
        super().__init__(id=card_id(device), classes="device-card")
        self.device = device
        self.busy = False

    def compose(self) -> ComposeResult:
        with Horizontal(classes="card-label"):
            yield Static("", classes="card-name", markup=False)
            yield Static("", classes="card-battery")
        # Grey when muted; the Unmute button says the rest
        yield Static("", classes="card-volume")
        yield VolumeBar(classes="card-bar")
        # Blank, in the figure's and the bar's place on headphones with no sink: their Connect button says it
        yield Static("", classes="card-state")
        yield self._button("", "btn-mute")
        yield self._button("", "btn-bluetooth")

    @staticmethod
    def _button(label: str, name: str) -> Button:
        button = Button(label, classes=name)
        button.can_focus = False  # A click must not pull focus off the card
        return button

    def on_mount(self) -> None:
        self.update(self.device)

    def update(self, device: Device, busy: bool | None = None) -> None:
        """Show new values for the same device."""
        self.device = device
        if busy is not None:
            self.busy = busy
        self.set_class(device.default, "-default")
        self.set_class(device.muted, "-muted")
        self.query_one(".card-name", Static).update(device.label)
        self.query_one(".card-battery", Static).update(battery_text(device.battery) if device.battery is not None else "")
        self._fit_battery()

        bluetooth = self.query_one(".btn-bluetooth", Button)
        # Hidden but still taking its room, so the columns of wired devices line up with the headphones';
        # MixerView drops the column altogether when there are no headphones
        bluetooth.visible = bool(device.mac)
        bluetooth.label = "Wait..." if self.busy else "Disconnect" if device.connected else "Connect"
        bluetooth.disabled = self.busy

        bar = self.query_one(".card-bar", VolumeBar)
        bar.set_volume(device.volume)
        volume = self.query_one(".card-volume", Static)
        volume.update(f"{device.volume}%")
        state = self.query_one(".card-state", Static)
        bar.display = volume.display = device.playable
        state.display = not device.playable
        mute = self.query_one(".btn-mute", Button)
        mute.display = device.playable
        mute.label = "Unmute" if device.muted else "Mute"
        mute.set_class(device.muted, "-unmute")

    def on_resize(self) -> None:
        self._fit_battery()

    def _fit_battery(self) -> None:
        """Show the battery only when it fits whole next to the name; a cut one says nothing."""
        battery = self.query_one(".card-battery", Static)
        room = self.query_one(".card-label").content_size.width - len(self.device.label)
        battery.display = self.device.battery is not None and room >= len(battery_text(self.device.battery)) + 2

    def action_volume(self, step: int) -> None:
        if self.device.playable:
            self.post_message(VolumeRequested(self.device, step_volume(self.device.volume, step)))

    def action_mute(self) -> None:
        if self.device.playable:
            self.post_message(MuteRequested(self.device))

    def action_use(self) -> None:
        """Switch to the device; headphones that are not connected get connected first."""
        device = self.device
        if device.default:
            return
        if device.playable:
            self.post_message(DefaultRequested(device))
        elif not device.connected:
            self.post_message(BluetoothRequested(device, use=True))

    def action_bluetooth(self) -> None:
        if self.device.mac and not self.busy:
            self.post_message(BluetoothRequested(self.device))

    def on_mouse_move(self) -> None:
        # The highlight follows the pointer, as it does the arrow keys
        if not self.has_focus:
            self.focus()

    def on_click(self, event: events.Click) -> None:
        """A click on the highlighted stretch uses the device, except on the bar, where it sets the volume."""
        self.focus()
        target, _ = self.screen.get_widget_at(event.screen_x, event.screen_y)
        bar = self.query_one(".card-bar", VolumeBar)
        if target is bar:
            volume = bar.volume_at(event.screen_x - bar.content_region.x)
            if self.device.playable and volume != self.device.volume:
                self.post_message(VolumeRequested(self.device, volume))
        elif any(target.has_class(name) for name in HIGHLIGHTED):
            self.action_use()

    @on(Button.Pressed, ".btn-mute")
    def _mute_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.focus()
        self.action_mute()

    @on(Button.Pressed, ".btn-bluetooth")
    def _bluetooth_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.focus()
        self.action_bluetooth()
