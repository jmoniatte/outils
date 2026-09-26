import asyncio
import io
import json
import socket
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from textual.app import App, ComposeResult
from textual.widgets import Input

from outils.app import OutilsApp, load_stylesheet
from outils.config import Config
from outils.ipinfo import IpInfoError, fetch, resolve, rows
from outils.widgets import IpView
from outils.widgets.ip_view import LABEL, IpDetails
from tui_kit.theme import load_palette

ANSWER = {
    "ip": "97.115.117.246",
    "hostname": "97-115-117-246.ptld.qwest.net",
    "city": "Portland",
    "region": "Oregon",
    "country": "US",
    "loc": "45.5234,-122.6762",
    "org": "AS209 CenturyLink Communications, LLC",
    "postal": "97204",
    "timezone": "America/Los_Angeles",
    "readme": "https://ipinfo.io/missingauth",
}


class IpInfoTest(unittest.TestCase):
    def test_rows_keep_the_known_fields_in_order_and_skip_missing_ones(self):
        self.assertEqual(
            rows(ANSWER),
            [
                ("IP", "97.115.117.246"),
                ("Hostname", "97-115-117-246.ptld.qwest.net"),
                ("City", "Portland"),
                ("Region", "Oregon"),
                ("Country", "US"),
                ("Postal code", "97204"),
                ("Location", "45.5234,-122.6762"),
                ("Time zone", "America/Los_Angeles"),
                ("Network", "AS209 CenturyLink Communications, LLC"),
            ],
        )
        self.assertEqual(rows({"ip": "1.2.3.4", "hostname": ""}), [("IP", "1.2.3.4")])

    def test_fetch_reads_the_answer_and_turns_failures_into_errors(self):
        with patch("outils.ipinfo.urlopen", return_value=io.BytesIO(json.dumps(ANSWER).encode())) as urlopen:
            self.assertEqual(fetch()["ip"], "97.115.117.246")
        self.assertEqual(urlopen.call_args.args[0], "https://ipinfo.io/json")
        for failure, message in (
            (URLError("no network"), "Cannot reach ipinfo.io: no network"),
            (HTTPError("u", 429, "Too many", {}, io.BytesIO()), "answered 429"),
        ):
            with patch("outils.ipinfo.urlopen", side_effect=failure), self.assertRaisesRegex(IpInfoError, message):
                fetch()
        with patch("outils.ipinfo.urlopen", return_value=io.BytesIO(b"<html>")), self.assertRaisesRegex(IpInfoError, "JSON"):
            fetch()
        with patch("outils.ipinfo.urlopen", return_value=io.BytesIO(b"{}")), self.assertRaisesRegex(IpInfoError, "address"):
            fetch()


    def test_fetch_asks_about_an_address_or_a_host_name_and_refuses_private_ones(self):
        def asked(target):
            with patch("outils.ipinfo.urlopen", return_value=io.BytesIO(json.dumps(ANSWER).encode())) as urlopen:
                fetch(target)
            return urlopen.call_args.args[0]

        self.assertEqual(asked("8.8.8.8"), "https://ipinfo.io/8.8.8.8/json")
        self.assertEqual(asked("2001:4860:4860::8888"), "https://ipinfo.io/2001:4860:4860::8888/json")
        with patch("outils.ipinfo.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("142.250.69.206", 0))]) as lookup:
            self.assertEqual(asked("google.com"), "https://ipinfo.io/142.250.69.206/json")
        lookup.assert_called_once_with("google.com.", None)
        self.assertEqual(resolve("8.8.8.8"), "8.8.8.8")
        with patch("outils.ipinfo.urlopen") as urlopen:
            with self.assertRaisesRegex(IpInfoError, "192.168.1.1 is a private address"):
                fetch("192.168.1.1")
            with (
                patch("outils.ipinfo.socket.getaddrinfo", side_effect=socket.gaierror("unknown")),
                self.assertRaisesRegex(IpInfoError, "Not an IP address or a known host name: nowhere"),
            ):
                fetch("nowhere")
            urlopen.assert_not_called()


class Host(App):
    CSS = load_stylesheet()
    AUTO_FOCUS = None

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**super().get_css_variables(), **load_palette("onedark")}

    def compose(self) -> ComposeResult:
        yield IpView(Config())

    def notify(self, message, **kwargs) -> None:
        self.messages.append(message)


async def settle(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


class IpViewTest(unittest.TestCase):
    def run_view(self, body, **patches):
        async def main():
            app = Host()
            with patch("outils.widgets.ip_view.fetch", **patches) as fetch:
                async with app.run_test(size=(90, 24)) as pilot:
                    await settle(app, pilot)
                    await body(app, pilot, fetch)

        asyncio.run(main())

    def test_shows_the_address_in_the_box_then_a_row_per_field_the_address_first(self):
        async def body(app, pilot, fetch):
            fetch.assert_called_once_with("")
            box = app.query_one("#ip-address", Input)
            self.assertEqual(box.value, "97.115.117.246")
            self.assertTrue(box.has_class("-found"))
            self.assertEqual(box.styles.color.hex.lower(), app.get_css_variables()["blue"].lower())
            details = app.query_one(IpDetails)
            text = details.render()
            lines = text.plain.split("\n")
            self.assertEqual(lines[:2], ["IP           97.115.117.246", "Hostname     97-115-117-246.ptld.qwest.net"])
            address = next(span for span in text.spans if text.plain[span.start:span.end] == "97.115.117.246")
            self.assertEqual(address.style, details.get_component_rich_style("ip--address"))
            self.assertEqual(lines[-1], "Network      AS209 CenturyLink Communications, LLC")
            self.assertEqual(len(lines), 9)
            # The box starts where the values do
            self.assertEqual(box.region.x, details.region.x + LABEL)

        self.run_view(body, return_value=ANSWER)

    def test_an_address_typed_in_the_box_is_looked_up_and_an_empty_box_asks_about_this_computer(self):
        async def body(app, pilot, fetch):
            box = app.query_one("#ip-address", Input)
            await pilot.click("#ip-address")
            self.assertIs(app.focused, box)
            self.assertFalse(box.has_class("-found"))
            box.value = ""
            await pilot.press(*"8.8.8.8", "enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_args.args, ("8.8.8.8",))
            self.assertIsNone(app.focused)
            # A host name stays in the box as typed
            box.value = ""
            await pilot.click("#ip-address")
            await pilot.press(*"example.com", "enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_args.args, ("example.com",))
            self.assertEqual(box.value, "example.com")
            self.assertTrue(box.has_class("-found"))
            box.value = "  "
            await pilot.click("#ip-address")
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_args.args, ("",))
            self.assertEqual(box.value, "97.115.117.246")
            # Escape leaves the box without asking, and without quitting
            await pilot.click("#ip-address")
            await pilot.press("escape")
            self.assertIsNone(app.focused)
            self.assertTrue(app.is_running)
            self.assertEqual(fetch.call_count, 4)

        self.run_view(body, return_value=ANSWER)

    def test_an_error_shows_in_place_of_the_details_and_not_in_the_header(self):
        async def body(app, pilot, fetch):
            details = app.query_one(IpDetails)
            self.assertEqual(details.render().plain, "Cannot reach ipinfo.io: no network")
            self.assertEqual(details.render().style, details.get_component_rich_style("ip--error"))
            self.assertEqual(details.get_component_rich_style("ip--error").color.triplet.hex.lower(), app.get_css_variables()["red"].lower())
            self.assertEqual(app.messages, [])

        self.run_view(body, side_effect=IpInfoError("Cannot reach ipinfo.io: no network"))

    def test_outils_ip_opens_the_ip_mode(self):
        async def main():
            app = OutilsApp("ip", Config(theme="onedark"))
            with patch("outils.widgets.ip_view.fetch", return_value=ANSWER):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    self.assertEqual(app.mode, "ip")
                    self.assertTrue(app.query_one(IpView).asked)

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
