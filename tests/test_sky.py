import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from outils.sky import full_moon, sun

PORTLAND = ZoneInfo("America/Los_Angeles")


class SkyTest(unittest.TestCase):
    def test_sunrise_and_sunset_within_two_minutes_of_the_almanac(self):
        # Open-Meteo gives 7:05 and 6:56pm on 2026-09-28; summer and winter in Portland, then Sydney
        rise, set_ = sun(date(2026, 9, 28), 45.52, -122.68, PORTLAND)
        self.assertLess(abs(rise - datetime(2026, 9, 28, 7, 5, tzinfo=PORTLAND)).total_seconds(), 120)
        self.assertLess(abs(set_ - datetime(2026, 9, 28, 18, 56, tzinfo=PORTLAND)).total_seconds(), 120)
        self.assertEqual([f"{t:%H:%M}" for t in sun(date(2026, 6, 21), 45.52, -122.68, PORTLAND)], ["05:21", "21:03"])
        self.assertEqual([f"{t:%H:%M}" for t in sun(date(2026, 12, 21), 45.52, -122.68, PORTLAND)], ["07:47", "16:29"])
        sydney = sun(date(2026, 3, 20), -33.87, 151.2, ZoneInfo("Australia/Sydney"))
        self.assertEqual([f"{t:%H:%M}" for t in sydney], ["06:57", "19:07"])
        # The midnight sun: no rise, no set
        self.assertEqual(sun(date(2026, 6, 21), 78.2, 15.6, ZoneInfo("Arctic/Longyearbyen")), (None, None))

    def test_the_moon_is_full_on_the_day_it_is_full_where_it_is_seen(self):
        # 2026-09-26 16:49 UTC and 2026-10-26 04:12 UTC, the 25th in Portland
        self.assertEqual([day for day in range(24, 29) if full_moon(date(2026, 9, day), PORTLAND)], [26])
        self.assertEqual([day for day in range(24, 29) if full_moon(date(2026, 10, day), PORTLAND)], [25])
        self.assertTrue(full_moon(date(2026, 10, 26), ZoneInfo("Europe/Paris")))
        # 2027-01-22 12:17 UTC, and 2000-01-21 04:40 UTC, the first after the count starts
        self.assertTrue(full_moon(date(2027, 1, 22), ZoneInfo("UTC")))
        self.assertTrue(full_moon(date(2000, 1, 21), ZoneInfo("UTC")))

if __name__ == "__main__":
    unittest.main()
