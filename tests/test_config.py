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


if __name__ == "__main__":
    unittest.main()
