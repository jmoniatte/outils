import unittest
from datetime import date

from outils.public_holidays import on, region_code
from outils.weather import Place

PORTLAND = Place("Portland", "Oregon", "United States", 45.52, -122.68, "America/Los_Angeles", "US")
MONTREAL = Place("Montréal", "Quebec", "Canada", 45.5, -73.6, "America/Toronto", "CA")
STRASBOURG = Place("Strasbourg", "Grand Est", "France", 48.58, 7.75, "Europe/Paris", "FR")


class PublicHolidaysTest(unittest.TestCase):
    def test_a_place_has_its_country_s_holidays_and_its_state_s_in_the_us_and_canada(self):
        self.assertEqual([region_code(place) for place in (PORTLAND, MONTREAL, STRASBOURG)], ["OR", "QC", ""])
        self.assertEqual(on(date(2026, 11, 26), PORTLAND), ["Thanksgiving Day"])
        # In the place's own language: French in France, and in Quebec though Canada's is English
        self.assertEqual(on(date(2026, 6, 24), MONTREAL), ["Fête nationale du Québec"])
        self.assertEqual(on(date(2026, 7, 14), STRASBOURG), ["Fête nationale"])
        # No place, or a country the package does not have: none
        self.assertEqual(on(date(2026, 12, 25), None), [])
        self.assertEqual(on(date(2026, 12, 25), Place("X", "", "", 0, 0, "UTC", "ZZ")), [])


if __name__ == "__main__":
    unittest.main()
