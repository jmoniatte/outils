import asyncio
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from textual.app import App, ComposeResult

from outils.app import OutilsApp, load_stylesheet
from outils.config import Config
from outils.ipinfo import IpInfoError, fetch, rows
from outils.widgets import IpView
from ouikit.theme import load_palette

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
        with patch("outils.ipinfo.urlopen", return_value=io.BytesIO(json.dumps(ANSWER).encode())):
            self.assertEqual(fetch()["ip"], "97.115.117.246")
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


class Host(App):
    CSS = load_stylesheet()

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**super().get_css_variables(), **load_palette("onedark")}

    def compose(self) -> ComposeResult:
        yield IpView(Config())

    def notify(self, message, **kwargs) -> None:
        self.messages.append(message)


class IpViewTest(unittest.TestCase):
    def run_view(self, body, **patches):
        async def main():
            app = Host()
            with patch("outils.widgets.ip_view.fetch", **patches):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    await body(app)

        asyncio.run(main())

    def test_shows_a_row_per_field_the_address_first_and_in_blue(self):
        async def body(app):
            view = app.query_one(IpView)
            text = view.render()
            lines = text.plain.split("\n")
            self.assertEqual(lines[0], "IP           97.115.117.246")
            self.assertEqual(lines[-1], "Network      AS209 CenturyLink Communications, LLC")
            self.assertEqual(len(lines), 9)
            address = next(span for span in text.spans if text.plain[span.start:span.end] == "97.115.117.246")
            self.assertEqual(address.style, view.get_component_rich_style("ip--address"))

        self.run_view(body, return_value=ANSWER)

    def test_an_error_shows_in_the_view_and_the_header(self):
        async def body(app):
            self.assertEqual(app.query_one(IpView).render().plain, "Cannot reach ipinfo.io: no network")
            self.assertEqual(app.messages, ["Cannot reach ipinfo.io: no network"])

        self.run_view(body, side_effect=IpInfoError("Cannot reach ipinfo.io: no network"))

    def test_outils_ip_opens_the_ip_mode(self):
        async def main():
            app = OutilsApp("ip", Config(theme="onedark"))
            with patch("outils.widgets.ip_view.fetch", return_value=ANSWER):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    self.assertEqual(app.query_one("#mode-name").render().plain, "IP")
                    self.assertEqual(len(app.query(IpView)), 1)

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
