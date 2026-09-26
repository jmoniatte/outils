import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tui_kit.header_notification import HeaderNotification
from tui_kit.help_screen import HelpScreen

from outils.app import OutilsApp
from outils.bluetooth import Headset
from outils.config import Config
from outils.pactl import SINK, SOURCE, Device, Mixer, PactlError
from outils.widgets import SoundView
from outils.widgets.device_card import DeviceCard

LAPTOP = Device(SINK, 1, "laptop", "Laptop speakers", 80, False, default=True)
MONITOR = Device(SINK, 2, "hdmi", "Monitor", 100, False)
MIC = Device(SOURCE, 3, "mic", "Digital Microphone", 60, False, default=True)
MIXER = Mixer(outputs=[LAPTOP, MONITOR], inputs=[MIC])
SHOKZ_MAC = "A8:F5:E1:E4:7D:DA"
SHOKZ = Device(SINK, 4, "bluez_output.A8_F5_E1_E4_7D_DA.1", "OpenRun by Shokz", 60, False, mac=SHOKZ_MAC)


def header_message(app: OutilsApp) -> str:
    notification = app.screen.query_one(HeaderNotification)
    return notification.render().plain if notification.display else ""


def card(app: OutilsApp, device: Device) -> DeviceCard:
    return app.query_one(f"#device-{device.kind}-{device.index}", DeviceCard)


def text(app: OutilsApp, device: Device) -> list[str]:
    """What the card shows, part by part, leaving out what is hidden or empty."""
    parts = card(app, device).query(".card-name, .card-battery, .card-volume, .card-state, Button")
    return [str(part.label if hasattr(part, "label") else part.render()) for part in parts if part.display and part.visible and str(part.render())]


async def settle(app: OutilsApp, pilot) -> None:
    while True:
        await pilot.pause()
        if not any(worker.is_running for worker in app.workers):
            break
        await app.workers.wait_for_complete()
    await pilot.pause()


class FakeMixer:
    """Remembers volume and mute changes, so the reload after each one reads them back as pactl would."""

    def __init__(self, mixer: Mixer) -> None:
        self.mixer = mixer

    def __call__(self) -> Mixer:
        return self.mixer

    def change(self, device: Device, **values) -> None:
        def update(devices):
            return [replace(each, **values) if each.index == device.index else each for each in devices]

        self.mixer = Mixer(outputs=update(self.mixer.outputs), inputs=update(self.mixer.inputs))


class SoundTest(unittest.TestCase):
    def run_app(self, body, mixer=MIXER, set_default=None, headsets=(), width=100, height=34):
        """Run the app against a fake pactl and bluetoothctl; body gets the app, the pilot and the mocks."""
        fake = FakeMixer(mixer)
        paired = list(headsets)

        def connect(mac):
            paired[:] = [Headset(each.mac, each.name, True) for each in paired]
            fake.mixer = Mixer(outputs=[*fake.mixer.outputs, SHOKZ], inputs=fake.mixer.inputs)

        async def main():
            with (
                tempfile.TemporaryDirectory() as tmp,
                patch("outils.app.CONFIG_FILE", Path(tmp) / "config.yaml"),
                patch("outils.pactl.mixer", side_effect=fake),
                patch("outils.pactl.set_volume", side_effect=lambda device, volume: fake.change(device, volume=volume)) as set_volume,
                patch("outils.pactl.set_mute", side_effect=lambda device, muted: fake.change(device, muted=muted)) as set_mute,
                patch("outils.pactl.set_default", side_effect=set_default) as set_default_mock,
                patch("outils.status_bar.refresh") as refresh_bar,
                patch("outils.bluetooth.headsets", side_effect=lambda: list(paired)),
                patch("outils.bluetooth.connect", side_effect=connect) as connect_mock,
                patch("outils.bluetooth.disconnect") as disconnect_mock,
            ):
                mocks = {
                    "set_volume": set_volume,
                    "set_mute": set_mute,
                    "set_default": set_default_mock,
                    "refresh_bar": refresh_bar,
                    "connect": connect_mock,
                    "disconnect": disconnect_mock,
                }
                app = OutilsApp("sound", Config(theme="onedark"))
                async with app.run_test(size=(width, height)) as pilot:
                    await settle(app, pilot)
                    await body(app, pilot, mocks)

        asyncio.run(main())

    def test_lists_outputs_and_the_microphone(self):
        async def body(app, pilot, mocks):
            self.assertEqual(text(app, LAPTOP), ["Laptop speakers", "80%", "Mute"])
            self.assertEqual(text(app, MIC), ["Digital Microphone", "60%", "Mute"])
            self.assertIs(app.focused, card(app, LAPTOP))
            # The devices in use stay highlighted without the mouse or the keys on them
            highlight = app.get_css_variables()["bg-light"].lower()
            backgrounds = [card(app, device).query_one(".card-bar").styles.background.hex.lower() for device in (MONITOR, MIC)]
            self.assertEqual(backgrounds[1], highlight)
            self.assertNotEqual(backgrounds[0], highlight)

            # Help's Sound column lists the keys of the card in focus and of the view
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpScreen)
            keys = [key.render().plain for key in app.screen.query("#shortcuts-sound .shortcut-key")]
            self.assertEqual(keys, ["←", "→", "m", "enter", "c", "↓ ↑"])

        self.run_app(body, width=76)

    def test_the_battery_shows_only_when_it_fits_whole(self):
        mixer = Mixer(outputs=[LAPTOP, replace(SHOKZ, battery=40)])

        async def wide(app, pilot, mocks):
            self.assertEqual(text(app, SHOKZ)[:2], ["OpenRun by Shokz", "\U000f007d 40%"])
            # Wired devices keep the Bluetooth column's room, so every row lines up
            button = card(app, LAPTOP).query_one(".btn-bluetooth")
            self.assertEqual((button.display, button.visible), (True, False))

        async def narrow(app, pilot, mocks):
            self.assertEqual(text(app, SHOKZ)[:2], ["OpenRun by Shokz", "60%"])
            self.assertTrue(card(app, SHOKZ).query_one(".btn-bluetooth").region.right <= app.size.width)
            # Names are never cut: the name column is as wide as the longest one
            self.assertEqual(card(app, SHOKZ).query_one(".card-name").size.width, len("OpenRun by Shokz"))

        self.run_app(wide, mixer=mixer)
        self.run_app(narrow, mixer=mixer, width=72)

    def test_a_message_stays_on_one_line(self):
        async def body(app, pilot, mocks):
            app.notify("Playing on a device with a much longer name than any real one would have here")
            await pilot.pause()
            self.assertEqual(app.query_one(HeaderNotification).size.height, 1)

        self.run_app(body, width=78)

    def test_a_pactl_failure_while_reloading_is_said_once_in_the_header(self):
        async def body(app, pilot, mocks):
            with patch("outils.pactl.mixer", side_effect=PactlError("Connection failure: Connection refused")):
                app.query_one(SoundView).load_mixer()
                await settle(app, pilot)
                self.assertEqual(header_message(app), "Connection failure: Connection refused")
                app.query_one(HeaderNotification).clear_notification()
                app.query_one(SoundView).load_mixer()
                await settle(app, pilot)
                self.assertEqual(header_message(app), "")

        self.run_app(body)

    def test_opens_on_the_output_in_use(self):
        async def body(app, pilot, mocks):
            self.assertIs(app.focused, card(app, MONITOR))

        self.run_app(body, mixer=Mixer(outputs=[replace(LAPTOP, default=False), replace(MONITOR, default=True)], inputs=[MIC]))

    def test_no_microphone_hides_its_section(self):
        async def body(app, pilot, mocks):
            self.assertEqual(len(app.query(DeviceCard)), 1)
            self.assertFalse(app.query_one("#inputs-cards").display)

        self.run_app(body, mixer=Mixer(outputs=[LAPTOP]))

    def test_arrows_change_the_volume_and_m_mutes_then_the_bar_is_told(self):
        async def body(app, pilot, mocks):
            await pilot.press("left", "left", "right")
            await settle(app, pilot)
            self.assertEqual([call.args[1] for call in mocks["set_volume"].call_args_list], [75, 70, 75])

            await pilot.press("m")
            await settle(app, pilot)
            mocks["set_mute"].assert_called_once_with(replace(LAPTOP, volume=75), True)
            # The figure stays and turns grey; Unmute says it is muted
            self.assertEqual(text(app, LAPTOP)[1:], ["75%", "Unmute"])
            volume_color = card(app, LAPTOP).query_one(".card-volume").styles.color.hex.lower()
            self.assertEqual(volume_color, app.get_css_variables()["comment"].lower())
            # Muting changes no name's color: green for the device in use, plain for the rest
            palette = app.get_css_variables()
            await pilot.press("down", "m")
            await settle(app, pilot)
            colors = [card(app, device).query_one(".card-name").styles.color.hex.lower() for device in (LAPTOP, MONITOR)]
            self.assertEqual(colors, [palette["green"].lower(), palette["fg"].lower()])
            self.assertEqual(mocks["refresh_bar"].call_count, 5)

        self.run_app(body)

    def test_a_volume_set_elsewhere_snaps_to_a_multiple_of_5(self):
        async def body(app, pilot, mocks):
            await pilot.press("right")
            await settle(app, pilot)
            await pilot.press("left", "left")
            await settle(app, pilot)
            self.assertEqual([call.args[1] for call in mocks["set_volume"].call_args_list], [65, 60, 55])

        self.run_app(body, mixer=Mixer(outputs=[replace(LAPTOP, volume=61)]))

    def test_the_highlight_follows_the_mouse_and_a_click_on_it_uses_the_device(self):
        async def body(app, pilot, mocks):
            await pilot.hover(card(app, MONITOR).query_one(".card-name"))
            await pilot.pause()
            self.assertIs(app.focused, card(app, MONITOR))
            mocks["set_default"].assert_not_called()

            # The buttons do their own thing and do not switch device
            await pilot.click(card(app, MONITOR).query_one(".btn-mute"))
            await settle(app, pilot)
            mocks["set_mute"].assert_called_once_with(MONITOR, True)
            self.assertEqual(text(app, MONITOR)[-1], "Unmute")
            mocks["set_default"].assert_not_called()

            # Anywhere on the highlight, the percentage included, uses the device
            await pilot.click(card(app, MONITOR).query_one(".card-volume"))
            await settle(app, pilot)
            self.assertEqual(mocks["set_default"].call_args.args[0].name, "hdmi")

            # Except the bar: half way along it is 50%
            bar = card(app, LAPTOP).query_one(".card-bar")
            await pilot.click(bar, offset=(bar.content_size.width // 2 - 1, 0))
            await settle(app, pilot)
            mocks["set_volume"].assert_called_once_with(LAPTOP, 50)

            # Past the buttons is outside the highlight: nothing
            laptop = card(app, LAPTOP)
            await pilot.click(laptop, offset=(laptop.size.width - 1, 0))
            await settle(app, pilot)
            self.assertEqual(mocks["set_default"].call_count, 1)

        self.run_app(body)

    def test_clicking_disconnected_headphones_connects_and_switches_to_them(self):
        async def body(app, pilot, mocks):
            offline = app.query_one("#outputs-cards").query(DeviceCard).last()
            self.assertEqual(text(app, offline.device), ["OpenRun by Shokz", "Connect"])

            # While it connects, the header says so
            connect, seen = mocks["connect"].side_effect, []
            mocks["connect"].side_effect = lambda mac: (seen.append(header_message(app)), connect(mac))

            # Volume keys do nothing on a card with no sink behind it
            await pilot.press("down", "down", "right", "m")
            self.assertIs(app.focused, offline)
            await pilot.click(offline.query_one(".card-name"))
            await settle(app, pilot)
            mocks["set_volume"].assert_not_called()
            mocks["set_mute"].assert_not_called()
            mocks["connect"].assert_called_once_with(SHOKZ_MAC)
            self.assertEqual(seen, ["Connecting to OpenRun by Shokz..."])
            mocks["set_default"].assert_called_once_with(SHOKZ)
            self.assertEqual(header_message(app), "Playing on OpenRun by Shokz")
            self.assertEqual(text(app, SHOKZ), ["OpenRun by Shokz", "60%", "Mute", "Disconnect"])

            await pilot.click(card(app, SHOKZ).query_one(".btn-bluetooth"))
            await settle(app, pilot)
            mocks["disconnect"].assert_called_once_with(SHOKZ_MAC)

        self.run_app(body, headsets=[Headset(SHOKZ_MAC, "OpenRun by Shokz", False)])

    def test_down_moves_into_the_microphone_section(self):
        async def body(app, pilot, mocks):
            await pilot.press("down", "down", "m")
            await settle(app, pilot)
            mocks["set_mute"].assert_called_once_with(MIC, True)

        self.run_app(body)

    def test_enter_uses_a_device_and_reports_errors(self):
        async def body(app, pilot, mocks):
            await pilot.press("j", "enter")
            await settle(app, pilot)
            mocks["set_default"].assert_called_once_with(MONITOR)
            self.assertEqual(header_message(app), "Failure: No such entity")
            mocks["refresh_bar"].assert_not_called()

        self.run_app(body, set_default=PactlError("Failure: No such entity"))


if __name__ == "__main__":
    unittest.main()
