import asyncio
import contextlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import TabbedContent, TabPane
from tui_kit.dialog import ConfirmDialog
from tui_kit.theme import load_palette

from outils.app import FooterMessage, OutilsApp
from outils.config import Config
from outils.nmcli import Details, Network, NmcliError, Scan, Share
from outils.qr import wifi_qr
from outils.screens import DetailsScreen, PasswordScreen, ShareScreen
from outils.screens.qr_screen import QrScreen
from outils.widgets import WifiView
from outils.widgets.networks_table import NetworksTable
from outils.widgets.wifi_view import LOGIN_PAGE_URL
from outils.wifi_operations import Operations
from tests.host import footer_message, settle

HOME = Network("Home", signal=70, security="WPA3", frequency=6295, in_use=True, saved_uuid="u1")
CAFE = Network("Cafe", signal=90, security="WPA2", frequency=2437)
WORK = Network("Work", signal=60, security="WPA2", frequency=5180, saved_uuid="u2")
OFFICE = Network("Office", signal=40, security="WPA2 802.1X", frequency=2412)
OLD = Network("Old", signal=0, security="", frequency=0, saved_uuid="u3", in_range=False)
DETAILS = Details("wlp1s0", "Home", "u1", "WPA3", 6295, 69, 70, addresses=("192.168.0.200/24",), gateway="192.168.0.1")
SCAN = Scan(nearby=[HOME, CAFE, WORK, OFFICE], saved=[HOME, WORK, OLD])


def status(app: OutilsApp) -> str:
    return str(app.query_one("#networks-status").render())


def nearby_table(app: OutilsApp) -> NetworksTable:
    return app.query_one("#nearby-table", NetworksTable)


class WifiTest(unittest.TestCase):
    def run_app(self, body, scan=SCAN, wifi=True, connect=None, details=DETAILS, connectivity="full", height=30):
        """Run the app against a fake nmcli; body gets the app, the pilot and the mocks."""

        async def main():
            with contextlib.ExitStack() as stack:
                tmp = stack.enter_context(tempfile.TemporaryDirectory())
                stack.enter_context(patch("outils.app.CONFIG_FILE", Path(tmp) / "config.yaml"))
                mocks = {
                    name: stack.enter_context(patch(f"outils.nmcli.{name}", **kwargs))
                    for name, kwargs in {
                        "wifi_enabled": {"return_value": wifi},
                        "set_wifi": {"return_value": None},
                        "connectivity": {"return_value": connectivity},
                        "scan": {"return_value": scan},
                        "connect": {"side_effect": connect} if connect else {"return_value": None},
                        "disconnect": {"return_value": "Home"},
                        "forget": {"return_value": None},
                        "details": {"return_value": details},
                        "share": {"return_value": Share("Home", "sae", "s3cret")},
                    }.items()
                }
                app = OutilsApp("wifi", Config(theme="onedark"))
                async with app.run_test(size=(110, height)) as pilot:
                    await settle(app, pilot)
                    await body(app, pilot, mocks)

        asyncio.run(main())

    def test_an_nmcli_failure_while_loading_is_said_once_in_the_footer(self):
        async def body(app, pilot, mocks):
            mocks["scan"].side_effect = NmcliError("NetworkManager is not running")
            view = app.query_one(WifiView)
            view.load_networks()
            await settle(app, pilot)
            self.assertEqual((footer_message(app), status(app)), ("NetworkManager is not running", "Scan failed"))
            app.query_one(FooterMessage).clear_notification()
            view.load_networks()
            await settle(app, pilot)
            self.assertEqual(footer_message(app), "")

        self.run_app(body)

    def test_lists_networks_with_the_current_one_first_and_marked(self):
        async def body(app, pilot, mocks):
            table = nearby_table(app)
            self.assertEqual(table.row_count, 4)
            self.assertEqual(table.cursor_row, 0)
            first = [str(cell) for cell in table.get_row_at(0)]
            self.assertEqual(first[:2], ["●", "Home"])
            self.assertEqual(first[3:], ["WPA3", "6 GHz"])
            tabs = app.query_one("#networks-tabs", TabbedContent)
            self.assertEqual([str(tabs.get_tab(tab).label) for tab in ("nearby", "saved")], ["Nearby (4)", "Saved (3)"])
            self.assertEqual(status(app), "")
            # The first load shows what NetworkManager last saw, then asks for a fresh scan
            self.assertEqual([call.args for call in mocks["scan"].call_args_list], [(), (True,)])

            # Enter on the network in use shows its details rather than connecting again
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertIsInstance(app.screen, DetailsScreen)
            mocks["connect"].assert_not_called()

        self.run_app(body)

    def test_a_new_network_asks_for_the_password_until_it_is_right(self):
        def connect(network, password=""):
            if password != "good":
                raise NmcliError("Secrets were required, but not provided")

        async def body(app, pilot, mocks):
            await pilot.press("j", "enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, PasswordScreen)

            await pilot.press(*"bad", "enter")
            await settle(app, pilot)
            self.assertIsInstance(app.screen, PasswordScreen)
            self.assertEqual(str(app.screen.query_one("#password-error").render()), "Secrets were required, but not provided")

            app.screen.query_one("#password").value = ""
            await pilot.press(*"good", "enter")
            await settle(app, pilot)
            self.assertNotIsInstance(app.screen, PasswordScreen)
            self.assertEqual(mocks["connect"].call_args.args, (CAFE, "good"))
            self.assertEqual(footer_message(app), "Connected to Cafe")

        self.run_app(body, connect=connect)

    def test_cancel_closes_the_password_dialog_but_the_connect_holds_until_nmcli_ends(self):
        release = threading.Event()

        def connect(network, password=""):
            release.wait(5)

        async def body(app, pilot, mocks):
            view = app.query_one(WifiView)
            await pilot.press("j", "enter")
            await pilot.pause()
            await pilot.press(*"pw", "enter")
            await pilot.pause()
            self.assertEqual(view.operations.change, "connecting to Cafe")

            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, PasswordScreen)
            self.assertEqual((view.operations.change, status(app)), ("connecting to Cafe", "Connecting to Cafe..."))

            # nmcli cannot be stopped midway, so nothing else may change the connection until it ends
            nearby_table(app).move_cursor(row=2)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(footer_message(app), "Still connecting to Cafe")

            release.set()
            await settle(app, pilot)
            self.assertIsNone(view.operations.change)
            self.assertEqual(footer_message(app), "Connected to Cafe")
            mocks["connect"].assert_called_once_with(CAFE, "pw")

        self.run_app(body, connect=connect)

    def test_connection_changes_run_one_at_a_time_until_nmcli_ends(self):
        release = threading.Event()

        async def body(app, pilot, mocks):
            mocks["connect"].side_effect = lambda network, password="": release.wait(5)
            mocks["disconnect"].side_effect = lambda: release.wait(5) and "Home"
            view = app.query_one(WifiView)
            nearby_table(app).move_cursor(row=2)
            await pilot.press("enter", "d")
            await pilot.pause()
            self.assertEqual(footer_message(app), "Still connecting to Work")
            mocks["disconnect"].assert_not_called()
            release.set()
            await settle(app, pilot)
            mocks["connect"].assert_called_once_with(WORK, "")

            # And the other way round: a connect waits for the disconnect
            release.clear()
            await pilot.press("d", "enter")
            await pilot.pause()
            self.assertEqual((footer_message(app), status(app)), ("Still disconnecting", "Disconnecting..."))
            mocks["connect"].assert_called_once()
            release.set()
            await settle(app, pilot)
            self.assertEqual((footer_message(app), status(app)), ("Disconnected from Home", ""))
            self.assertIsNone(view.operations.change)

        self.run_app(body)

    def test_rescans_never_overlap(self):
        gate = threading.Event()
        lock = threading.Lock()
        rescans = {"running": 0, "most": 0, "calls": 0}

        def scan(rescan=False):
            if rescan:
                with lock:
                    rescans["running"] += 1
                    rescans["calls"] += 1
                    rescans["most"] = max(rescans["most"], rescans["running"])
                gate.wait(5)
                with lock:
                    rescans["running"] -= 1
            return SCAN

        async def body(app, pilot, mocks):
            mocks["scan"].side_effect = scan
            await pilot.press("r")
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            self.assertEqual(status(app), "Scanning...")
            gate.set()
            await settle(app, pilot)
            self.assertEqual((rescans["most"], rescans["calls"], status(app)), (1, 1, ""))

        self.run_app(body)

    def test_a_saved_network_connects_on_click_without_asking(self):
        async def body(app, pilot, mocks):
            table = nearby_table(app)
            await pilot.click("#nearby-table", offset=(10, 2))
            await settle(app, pilot)
            self.assertEqual(table.cursor_row, 2)
            self.assertNotIsInstance(app.screen, PasswordScreen)
            mocks["connect"].assert_called_once_with(WORK, "")
            self.assertEqual(footer_message(app), "Connected to Work")

        self.run_app(body)

    def test_a_failed_saved_connect_points_at_forget(self):
        async def body(app, pilot, mocks):
            nearby_table(app).move_cursor(row=2)
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertEqual(
                footer_message(app),
                "Could not connect to Work: Timed out. Press f to forget it and enter the password again",
            )
            self.assertIsNone(app.query_one(WifiView).operations.change)

        self.run_app(body, connect=NmcliError("Timed out"))

    def test_enterprise_networks_are_not_offered_a_password_prompt(self):
        async def body(app, pilot, mocks):
            nearby_table(app).move_cursor(row=3)
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertNotIsInstance(app.screen, PasswordScreen)
            self.assertIn("802.1X", footer_message(app))

        self.run_app(body)

    def test_forget_asks_first_and_disconnect_does_not(self):
        async def body(app, pilot, mocks):
            await pilot.press("f")
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmDialog)
            await pilot.press("escape")
            await pilot.pause()
            mocks["forget"].assert_not_called()
            self.assertTrue(app.is_running)

            await pilot.press("f")
            await pilot.pause()
            await pilot.click("#confirm-btn")
            await settle(app, pilot)
            mocks["forget"].assert_called_once_with(HOME)
            self.assertEqual(footer_message(app), "Forgot Home")

            nearby_table(app).move_cursor(row=1)
            await pilot.press("f")
            await settle(app, pilot)
            self.assertEqual(footer_message(app), "Cafe is not saved")

            await pilot.press("d")
            await settle(app, pilot)
            mocks["disconnect"].assert_called_once()
            self.assertEqual(footer_message(app), "Disconnected from Home")

        self.run_app(body)

    def test_the_saved_list_lists_every_profile_and_forgets_ones_out_of_range(self):
        async def body(app, pilot, mocks):
            # The arrows switch lists: tab moves between outils' own tabs
            await pilot.press("right")
            await pilot.pause()
            saved = app.query_one("#saved-table", NetworksTable)
            self.assertTrue(saved.has_focus)
            self.assertEqual([str(saved.get_row_at(row)[1]) for row in range(saved.row_count)], ["Home", "Work", "Old"])
            self.assertEqual(str(saved.get_row_at(2)[3]), "not in range")

            # A saved network not in use shows only its password and a QR code button, even out of range
            saved.move_cursor(row=2)
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertIsInstance(app.screen, ShareScreen)
            self.assertEqual([pane.id for pane in app.screen.query(TabPane)], ["password"])
            self.assertEqual(str(app.screen.query_one(".share-password").render()), "s3cret")
            mocks["share"].assert_called_once_with("u3")
            mocks["connect"].assert_not_called()
            await pilot.press("escape")
            await pilot.pause()

            # The one in use still opens the full panel
            saved.move_cursor(row=0)
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertIsInstance(app.screen, DetailsScreen)
            await pilot.press("escape")
            await pilot.pause()

            saved.move_cursor(row=2)
            await pilot.press("f")
            await pilot.pause()
            await pilot.click("#confirm-btn")
            await settle(app, pilot)
            mocks["forget"].assert_called_once_with(OLD)

            await pilot.press("left")
            await pilot.pause()
            self.assertTrue(nearby_table(app).has_focus)

        self.run_app(body)

    def test_two_profiles_for_one_network_are_two_saved_rows(self):
        home_too = Network("Home", signal=70, security="WPA3", frequency=6295, saved_uuid="u4")

        async def body(app, pilot, mocks):
            await pilot.press("right")
            await pilot.pause()
            saved = app.query_one("#saved-table", NetworksTable)
            self.assertEqual(saved.row_count, 4)
            saved.move_cursor(row=1)
            await pilot.press("enter")
            await settle(app, pilot)
            mocks["share"].assert_called_once_with("u4")
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("f")
            await pilot.pause()
            await pilot.click("#confirm-btn")
            await settle(app, pilot)
            mocks["forget"].assert_called_once_with(home_too)

        self.run_app(body, scan=Scan(nearby=[HOME, CAFE, WORK, OFFICE], saved=[HOME, home_too, WORK, OLD]))

    def test_details_show_the_password_and_qr_code_only_when_asked(self):
        async def body(app, pilot, mocks):
            await pilot.press("i")
            await settle(app, pilot)
            screen = app.screen
            self.assertIsInstance(screen, DetailsScreen)
            values = {
                str(row.query(".details-label").first().render()): str(row.query(".details-value").first().render())
                for row in screen.query("#details .details-row")
            }
            self.assertEqual(values["Band"], "6 GHz, channel 69")
            self.assertEqual(values["IP address"], "192.168.0.200/24")
            mocks["share"].assert_not_called()

            await pilot.press("p")
            await settle(app, pilot)
            self.assertEqual(screen.query_one(TabbedContent).active, "password")
            mocks["share"].assert_called_once_with("u1")
            self.assertEqual(str(screen.query_one(".share-password").render()), "s3cret")

            # Tab cycles through both without reading the password again
            active = []
            for _ in range(2):
                await pilot.press("tab")
                await settle(app, pilot)
                active.append(screen.query_one(TabbedContent).active)
            self.assertEqual(active, ["details", "password"])
            self.assertEqual(app.mode, "wifi")

            # The QR code opens alone over the whole window, so a short window fits it; any key closes it
            await pilot.press("c")
            await settle(app, pilot)
            self.assertIsInstance(app.screen, QrScreen)
            code = app.screen.query_one("#qr-code")
            self.assertEqual(str(code.render()), "\n".join(wifi_qr(Share("Home", "sae", "s3cret"))))
            self.assertEqual("".join(str(part.render()) for part in app.screen.query("#qr-hint Static")), "Scan to join Home")
            self.assertEqual(app.screen.query_one("#qr-ssid").styles.color.hex.lower(), app.get_css_variables()["blue"].lower())
            self.assertTrue(code.region.y >= 0 and app.screen.query_one("#qr-hint").region.bottom <= app.size.height)
            mocks["share"].assert_called_once()
            await pilot.press("x")
            await pilot.pause()
            self.assertIs(app.screen, screen)

        self.run_app(body)

    def test_the_qr_button_reads_the_password_first_and_fits_18_rows(self):
        async def body(app, pilot, mocks):
            await pilot.press("i")
            await settle(app, pilot)
            # The button is on the Password tab, under the password
            self.assertFalse(app.screen.query_one("#btn-qr").region)
            await pilot.click("#network-tabs Tab#--content-tab-password")
            await settle(app, pilot)
            await pilot.click("#btn-qr")
            await settle(app, pilot)
            self.assertIsInstance(app.screen, QrScreen)
            mocks["share"].assert_called_once_with("u1")
            self.assertLessEqual(app.screen.query_one("#qr-hint").region.bottom, 18)
            await pilot.click("#qr-code")
            await pilot.pause()
            self.assertIsInstance(app.screen, DetailsScreen)
            # The button takes no focus, so it comes back drawn as before, one background
            self.assertFalse(app.screen.query_one("#btn-qr").has_focus)

        self.run_app(body, height=18)

    def test_details_without_a_connection_say_so(self):
        async def body(app, pilot, mocks):
            await pilot.press("i")
            await settle(app, pilot)
            self.assertNotIsInstance(app.screen, DetailsScreen)
            self.assertEqual(footer_message(app), "Not connected to Wi-Fi")

        self.run_app(body, details=None)

    def test_escape_quits_from_the_list(self):
        async def body(app, pilot, mocks):
            await pilot.press("escape")
            await pilot.pause()
            self.assertFalse(app.is_running)

        self.run_app(body)

    def test_w_turns_wifi_on_from_an_empty_list_and_off_again(self):
        async def body(app, pilot, mocks):
            self.assertEqual(nearby_table(app).networks, [])
            self.assertEqual(status(app), "Wi-Fi is off")
            mocks["scan"].assert_not_called()

            wifi_button = app.query_one("#btn-wifi")
            self.assertEqual((str(wifi_button.label), wifi_button.has_class("-on")), ("Wi-Fi on", True))
            self.assertFalse(app.query_one("#btn-rescan").display)

            mocks["set_wifi"].side_effect = lambda on: setattr(mocks["wifi_enabled"], "return_value", on)
            wifi_button.press()
            await settle(app, pilot)
            mocks["set_wifi"].assert_called_with(True)
            self.assertEqual(footer_message(app), "Wi-Fi turned on")
            self.assertEqual(nearby_table(app).networks, SCAN.nearby)
            self.assertEqual(status(app), "")
            self.assertEqual((str(wifi_button.label), wifi_button.has_class("-off")), ("Wi-Fi off", True))
            self.assertTrue(app.query_one("#btn-rescan").display)

            await pilot.press("w")
            await settle(app, pilot)
            mocks["set_wifi"].assert_called_with(False)
            self.assertEqual(status(app), "Wi-Fi is off")

        self.run_app(body, wifi=False)

    def test_a_login_page_is_announced_and_o_opens_it(self):
        async def body(app, pilot, mocks):
            self.assertEqual(status(app), "Login page required: press o")
            with patch.object(app, "open_url") as open_url:
                await pilot.press("o")
                await settle(app, pilot)
            open_url.assert_called_once_with(LOGIN_PAGE_URL)

        self.run_app(body, connectivity="portal")

    def test_no_internet_is_announced_and_o_says_there_is_no_login_page(self):
        async def body(app, pilot, mocks):
            self.assertEqual(status(app), "No internet access")
            with patch.object(app, "open_url") as open_url:
                await pilot.press("o")
                await settle(app, pilot)
            open_url.assert_not_called()
            self.assertEqual(footer_message(app), "This network does not ask for a login page")

        self.run_app(body, connectivity="limited")

    def test_a_theme_change_repaints_the_lists(self):
        async def body(app, pilot, mocks):
            app.apply_theme("dracula")
            await pilot.pause()
            # The lists bake their colors into Rich text, so a theme change has to reach them too
            self.assertEqual(nearby_table(app)._colors.current, load_palette("dracula")["green"])

        self.run_app(body)

    def test_help_lists_the_apps_keys_then_the_wifi_ones(self):
        async def body(app, pilot, mocks):
            await pilot.press("question_mark")
            await pilot.pause()
            keys = [key.render().plain for key in app.screen.query("#shortcuts-wi-fi .shortcut-key")]
            self.assertIn("← →", keys)
            self.assertTrue({"r", "d", "f", "i", "w", "o", "p", "c"} <= set(keys))
            general = [key.render().plain for key in app.screen.query("#shortcuts-general .shortcut-key")]
            self.assertEqual(general, ["?", "t", "y", "tab", "q"])

        self.run_app(body)


class OperationsTest(unittest.TestCase):
    def test_a_change_holds_until_its_call_ends_even_when_its_awaiter_is_cancelled(self):
        release = threading.Event()

        async def main():
            operations = Operations(None)
            waiter = asyncio.ensure_future(operations.start("connecting to Cafe", lambda: release.wait(5)))
            self.assertIsNone(operations.start("disconnecting", lambda: None))
            await asyncio.sleep(0.05)
            waiter.cancel()
            await asyncio.sleep(0.05)
            self.assertEqual(operations.change, "connecting to Cafe")
            release.set()
            await asyncio.sleep(0.05)
            self.assertIsNone(operations.change)

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
