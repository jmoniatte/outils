import tempfile
import unittest
from datetime import date
from pathlib import Path

from outils.config import Birthday, Config, load_config, save_units


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "outils" / "config.yaml"

    def load(self, text: str) -> Config:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(text)
        return load_config(self.path)

    def test_reads_the_theme_and_a_missing_or_broken_file_means_defaults(self) -> None:
        self.assertEqual(load_config(self.path), Config())
        self.assertEqual(self.load("theme: one-light\n"), Config(theme="one-light"))
        unknown = self.load("theme: onelight\n")
        self.assertEqual(len(unknown.warnings), 1)
        self.assertIn("'onelight' is not installed", unknown.warnings[0])
        broken = self.load("theme: [unclosed\n")
        self.assertEqual(broken.theme, Config().theme)
        self.assertIn("not valid YAML", broken.warnings[0])

    def test_week_start_takes_a_day_name_and_defaults_to_monday(self) -> None:
        self.assertEqual(Config().week_start, 0)
        sunday = self.load("week_start: Sunday\n")
        self.assertEqual((sunday.week_start, sunday.warnings), (6, []))
        unknown = self.load("week_start: someday\n")
        self.assertEqual(unknown.week_start, 0)
        self.assertEqual(unknown.warnings, ["week_start: 'someday' is not a day of the week, using monday"])

    def test_location_and_units_are_read_and_bad_units_warn(self) -> None:
        self.assertEqual((Config().location, Config().units), ("Portland, OR", "metric"))
        set_up = self.load("location: ' Victoria, BC '\nunits: Imperial\n")
        self.assertEqual((set_up.location, set_up.units, set_up.warnings), ("Victoria, BC", "imperial", []))
        wrong = self.load("location: 42\nunits: kelvin\n")
        self.assertEqual((wrong.location, wrong.units), ("Portland, OR", "metric"))
        self.assertEqual(len(wrong.warnings), 2)
        self.assertIn("kelvin", wrong.warnings[1])

    def test_locations_are_a_list_and_the_first_opens(self) -> None:
        cities = self.load("locations:\n  - Portland, OR\n  - ' Chicago, IL '\n  - 42\nlocation: Victoria, BC\n")
        self.assertEqual((cities.locations, cities.location), (["Portland, OR", "Chicago, IL"], "Portland, OR"))
        self.assertEqual(cities.warnings, ["locations: '42' is not a place name, such as Victoria, BC"])
        wrong = self.load("locations: Chicago\n")
        self.assertEqual((wrong.locations, wrong.warnings), (["Portland, OR"], ["locations: must be a list of place names, such as Victoria, BC"]))

    def test_save_units_sets_the_units_that_load_config_reads(self) -> None:
        self.path.parent.mkdir()
        self.path.write_text("theme: nord\nunits: metric\n")
        self.assertIsNone(save_units("imperial", self.path))
        self.assertEqual(self.path.read_text(), "theme: nord\nunits: imperial\n")
        self.assertEqual(load_config(self.path).units, "imperial")

    def test_clocks_map_names_to_time_zones_in_order_and_bad_zones_warn(self) -> None:
        self.assertEqual([clock.name for clock in Config().clocks], ["Portland", "Chicago", "UTC", "Strasbourg"])
        set_up = self.load("clocks:\n  Tokyo: Asia/Tokyo\n  Home: Mars/Olympus\n  Paris: ' Europe/Paris '\n")
        self.assertEqual([(clock.name, clock.zone.key) for clock in set_up.clocks], [("Tokyo", "Asia/Tokyo"), ("Paris", "Europe/Paris")])
        self.assertEqual(set_up.warnings, ["clocks: 'Mars/Olympus' is not a time zone, such as Europe/Paris"])
        wrong = self.load("clocks: [Europe/Paris]\n")
        self.assertEqual(wrong.clocks, Config().clocks)
        self.assertEqual(len(wrong.warnings), 1)

    def test_birthdays_map_dates_to_names_every_year_and_bad_dates_warn(self) -> None:
        self.assertEqual(Config().birthdays, [])
        set_up = self.load("birthdays:\n  10-02: Mom\n  1990-10-15: Léa\n  02-29: Leap\n  13-01: Nope\n")
        self.assertEqual(set_up.birthdays, [Birthday("Mom", 10, 2), Birthday("Léa", 10, 15, 1990), Birthday("Leap", 2, 29)])
        self.assertEqual(set_up.warnings, ["birthdays: '13-01' is not a date, such as 10-02 or 1990-10-02"])
        # Every year from the year born, with the age that year
        lea = Birthday("Léa", 10, 15, 1990)
        self.assertEqual([lea.falls_on(date(year, 10, 15)) for year in (1989, 1990, 2027)], [False, True, True])
        self.assertEqual([lea.label(date(year, 10, 15)) for year in (1990, 2027)], ["Léa (born)", "Léa (37)"])
        self.assertEqual(Birthday("Mom", 10, 2).label(date(2027, 10, 2)), "Mom")
        self.assertEqual(len(self.load("birthdays: [10-02]\n").warnings), 1)


if __name__ == "__main__":
    unittest.main()
