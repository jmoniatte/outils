import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from outils.epoch import EpochError, parse, relative, rows

NOW = datetime(2026, 9, 25, 5, 4, tzinfo=UTC)
PORTLAND = ZoneInfo("America/Los_Angeles")


def convert(text):
    return dict(rows(parse(text, NOW, PORTLAND), NOW, PORTLAND))


class EpochTest(unittest.TestCase):
    def test_a_timestamp_is_seconds_or_milliseconds_with_13_digits(self):
        seconds = convert("1790222400")
        self.assertEqual(seconds["UTC"], "2026-09-24T04:00:00+00:00")
        self.assertEqual(seconds["Local"], "2026-09-23T21:00:00-07:00")
        self.assertEqual(seconds["Relative"], "1 day ago")
        fraction = convert("1790222400.123")
        self.assertEqual((fraction["Seconds"], fraction["UTC"], fraction["Local"]), ("1790222400.123", "2026-09-24T04:00:00.123+00:00", "2026-09-23T21:00:00.123-07:00"))
        millis = convert("1790222400123")
        self.assertEqual((millis["Seconds"], millis["UTC"]), ("1790222400.123", "2026-09-24T04:00:00.123+00:00"))
        # 12 digits are still seconds: year 5138, not 1973
        self.assertEqual(convert("100000000000")["UTC"], "5138-11-16T09:46:40+00:00")
        # Nothing longer than milliseconds
        with self.assertRaises(EpochError):
            parse("1790222400123456", NOW)
        self.assertEqual(convert("-1")["UTC"], "1969-12-31T23:59:59+00:00")
        self.assertEqual(convert("-1.5")["Seconds"], "-1.5")

    def test_a_date_is_local_time_unless_it_gives_an_offset(self):
        summer = convert("2026-09-24 15:30")
        self.assertEqual((summer["Seconds"], summer["UTC"]), ("1790289000", "2026-09-24T22:30:00+00:00"))
        self.assertEqual(convert("2026-01-15")["UTC"], "2026-01-15T08:00:00+00:00")
        self.assertEqual(convert("2026-01-15")["Local"], "2026-01-15T00:00:00-08:00")
        zulu = convert("2026-09-24T22:30Z")
        self.assertEqual(zulu["Seconds"], "1790289000")
        self.assertEqual(convert("2026-09-25T00:30:00+02:00")["Seconds"], "1790289000")
        # Empty, or now, is now
        self.assertEqual(convert("")["Relative"], "now")
        self.assertEqual(convert(" now ")["Relative"], "now")

    def test_what_is_neither_says_so(self):
        for text in ("abc", "1e5", "2026-13-01", "99999999999999999999999"):
            with self.subTest(text=text), self.assertRaises(EpochError):
                parse(text, NOW)

    def test_relative_takes_the_largest_unit(self):
        self.assertEqual(relative(datetime(2026, 9, 25, 7, 5, tzinfo=UTC), NOW), "in 2 hours")
        self.assertEqual(relative(datetime(2026, 9, 25, 5, 3, tzinfo=UTC), NOW), "1 minute ago")
        self.assertEqual(relative(datetime(2020, 1, 1, tzinfo=UTC), NOW), "6 years ago")


if __name__ == "__main__":
    unittest.main()
