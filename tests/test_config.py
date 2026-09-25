import tempfile
import unittest
from pathlib import Path

from outils.config import Config, load_config


class LoadConfigTest(unittest.TestCase):
    def test_reads_the_theme_and_a_missing_file_means_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("theme: one-light\n")
            self.assertEqual(load_config(path), Config(theme="one-light"))
            path.write_text("theme: onelight\n")
            unknown = load_config(path)
        self.assertEqual(len(unknown.warnings), 1)
        self.assertIn("'onelight' is not installed", unknown.warnings[0])
        self.assertEqual(load_config(Path("/nonexistent/config.yaml")), Config())

    def test_invalid_file_falls_back_to_defaults_with_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("theme: [unclosed\n")
            broken = load_config(path)
        self.assertEqual(broken.theme, Config().theme)
        self.assertIn("not valid YAML", broken.warnings[0])


class WeekStartTest(unittest.TestCase):
    def test_week_start_takes_a_day_name_and_defaults_to_monday(self) -> None:
        self.assertEqual(Config().week_start, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("week_start: Sunday\n")
            sunday = load_config(path)
            path.write_text("week_start: someday\n")
            unknown = load_config(path)
        self.assertEqual((sunday.week_start, sunday.warnings), (6, []))
        self.assertEqual(unknown.week_start, 0)
        self.assertEqual(unknown.warnings, ["week_start: 'someday' is not a day of the week, using monday"])


class WeatherConfigTest(unittest.TestCase):
    def test_location_and_units_are_read_and_bad_units_warn(self) -> None:
        self.assertEqual((Config().location, Config().units), ("Portland, OR", "metric"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("location: ' Victoria, BC '\nunits: Imperial\n")
            set_up = load_config(path)
            path.write_text("location: 42\nunits: kelvin\n")
            wrong = load_config(path)
        self.assertEqual((set_up.location, set_up.units, set_up.warnings), ("Victoria, BC", "imperial", []))
        self.assertEqual((wrong.location, wrong.units), ("Portland, OR", "metric"))
        self.assertEqual(len(wrong.warnings), 2)
        self.assertIn("kelvin", wrong.warnings[1])


class ClocksConfigTest(unittest.TestCase):
    def test_clocks_map_names_to_time_zones_in_order_and_bad_zones_warn(self) -> None:
        self.assertEqual([clock.name for clock in Config().clocks], ["Portland", "Chicago", "UTC", "Strasbourg"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("clocks:\n  Tokyo: Asia/Tokyo\n  Home: Mars/Olympus\n  Paris: ' Europe/Paris '\n")
            set_up = load_config(path)
            path.write_text("clocks: [Europe/Paris]\n")
            wrong = load_config(path)
        self.assertEqual([(clock.name, clock.zone.key) for clock in set_up.clocks], [("Tokyo", "Asia/Tokyo"), ("Paris", "Europe/Paris")])
        self.assertEqual(set_up.warnings, ["clocks: 'Mars/Olympus' is not a time zone, such as Europe/Paris"])
        self.assertEqual(wrong.clocks, Config().clocks)
        self.assertEqual(len(wrong.warnings), 1)


if __name__ == "__main__":
    unittest.main()
