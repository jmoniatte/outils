import unittest

import segno

from outils.nmcli import Share
from outils.qr import BORDER, wifi_qr


class WifiQrTest(unittest.TestCase):
    def test_half_blocks_redraw_the_code_module_for_module(self):
        share = Share("Home;1", "sae", "p:w")
        lines = wifi_qr(share)
        expected = segno.make(r"WIFI:T:WPA;S:Home\;1;P:p\:w;;", error="l")
        modules = [[bool(module) for module in row] for row in expected.matrix_iter(border=BORDER)]

        drawn = []
        for line in lines:
            drawn.append([char in "█▀" for char in line])
            drawn.append([char in "█▄" for char in line])
        self.assertEqual(drawn[: len(modules)], modules)
        self.assertEqual({len(line) for line in lines}, {len(modules[0])})


if __name__ == "__main__":
    unittest.main()
