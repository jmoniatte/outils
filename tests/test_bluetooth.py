import subprocess
import unittest
from unittest.mock import patch

from outils import bluetooth
from outils.bluetooth import BluetoothError, Headset
from outils.pactl import SINK, Device, Mixer

SHOKZ_INFO = """Device A8:F5:E1:E4:7D:DA (public)
\tName: OpenRun by Shokz
\tAlias: OpenRun by Shokz
\tIcon: audio-headphones
\tPaired: yes
\tConnected: yes
\tBattery Percentage: 0x50 (80)
"""
MOUSE_INFO = """Device D1:0C:BB:CA:E3:1C (random)
\tName: Logi M650
\tIcon: input-mouse
\tConnected: yes
"""


class BluetoothTest(unittest.TestCase):
    def test_lists_paired_audio_devices_only_with_their_battery(self):
        replies = {
            ("devices", "Paired"): "Device A8:F5:E1:E4:7D:DA OpenRun by Shokz\nDevice D1:0C:BB:CA:E3:1C Logi M650\n",
            ("info", "A8:F5:E1:E4:7D:DA"): SHOKZ_INFO,
            ("info", "D1:0C:BB:CA:E3:1C"): MOUSE_INFO,
        }
        with patch("outils.bluetooth.run", side_effect=lambda *args: replies[args]):
            self.assertEqual(bluetooth.headsets(), [Headset("A8:F5:E1:E4:7D:DA", "OpenRun by Shokz", True, 80)])
        with patch("outils.bluetooth.run", side_effect=BluetoothError("bluetoothctl is not installed")):
            self.assertEqual(bluetooth.headsets(), [])

    def test_merge_adds_the_battery_and_a_row_for_headphones_with_no_sink(self):
        laptop = Device(SINK, 1, "laptop", "Laptop speakers", 80, False, default=True)
        shokz = Device(SINK, 4, "bluez_output.A8_F5", "OpenRun by Shokz", 60, False, mac="A8:F5")
        merged = bluetooth.merge(
            Mixer(outputs=[laptop, shokz]),
            [Headset("A8:F5", "OpenRun by Shokz", True, 80), Headset("00:11", "Speaker", False)],
        )
        self.assertEqual([device.battery for device in merged.outputs], [None, 80, None])
        added = merged.outputs[2]
        self.assertEqual((added.label, added.mac, added.connected, added.playable), ("Speaker", "00:11", False, False))

    def test_failures_become_bluetooth_errors(self):
        # bluetoothctl prints its failures on stdout, sometimes with exit status 0
        failed = subprocess.CompletedProcess([], 0, "Attempting to connect to A8\nFailed to connect: org.bluez.Error.Failed\n", "")
        with patch("tui_kit.processes.run", return_value=failed), self.assertRaisesRegex(BluetoothError, "^Failed to connect"):
            bluetooth.connect("A8")
        missing = subprocess.CompletedProcess([], 1, "Device 00:11 not available\n", "")
        with patch("tui_kit.processes.run", return_value=missing), self.assertRaisesRegex(BluetoothError, "not available"):
            bluetooth.disconnect("00:11")


if __name__ == "__main__":
    unittest.main()
