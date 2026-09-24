import re
import unittest

from ouikit.theme import list_themes, load_palette

from outils.app import load_stylesheet


class ThemeTest(unittest.TestCase):
    def test_every_theme_fills_each_variable_the_stylesheets_use(self):
        required = set(re.findall(r"\$([\w-]+)", load_stylesheet()))
        self.assertIn("comment", required)
        for name in list_themes():
            with self.subTest(theme=name):
                self.assertEqual(required - set(load_palette(name)), set())


if __name__ == "__main__":
    unittest.main()
