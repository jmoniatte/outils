import tempfile
import unittest
from pathlib import Path

from outils.config import Config, load_config, save_units


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

    def test_save_units_replaces_the_units_line_or_adds_one_and_keeps_the_rest(self) -> None:
        save_units("imperial", self.path)
        self.assertEqual(self.path.read_text(), "units: imperial\n")
        self.path.write_text("theme: nord  # mine\nunits: imperial\nweek_start: sunday")
        save_units("metric", self.path)
        self.assertEqual(self.path.read_text(), "theme: nord  # mine\nunits: metric\nweek_start: sunday")
        self.path.write_text("theme: nord")
        save_units("metric", self.path)
        self.assertEqual(self.path.read_text(), "theme: nord\nunits: metric\n")
        self.assertEqual(load_config(self.path).units, "metric")

    def test_clocks_map_names_to_time_zones_in_order_and_bad_zones_warn(self) -> None:
        self.assertEqual([clock.name for clock in Config().clocks], ["Portland", "Chicago", "UTC", "Strasbourg"])
        set_up = self.load("clocks:\n  Tokyo: Asia/Tokyo\n  Home: Mars/Olympus\n  Paris: ' Europe/Paris '\n")
        self.assertEqual([(clock.name, clock.zone.key) for clock in set_up.clocks], [("Tokyo", "Asia/Tokyo"), ("Paris", "Europe/Paris")])
        self.assertEqual(set_up.warnings, ["clocks: 'Mars/Olympus' is not a time zone, such as Europe/Paris"])
        wrong = self.load("clocks: [Europe/Paris]\n")
        self.assertEqual(wrong.clocks, Config().clocks)
        self.assertEqual(len(wrong.warnings), 1)


if __name__ == "__main__":
    unittest.main()
