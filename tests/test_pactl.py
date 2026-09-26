import subprocess
import unittest
from unittest.mock import patch

from outils import pactl
from outils.pactl import SINK, SOURCE, Device, PactlError


def volume(*percents: int) -> dict:
    return {f"ch{i}": {"value_percent": f"{p}%"} for i, p in enumerate(percents)}


def sink(index: int, name: str, port_type: str, availability: str, description: str = "", **extra) -> dict:
    port = {"name": f"[Out] {port_type}{index}", "description": f"{port_type} Output {index}", "type": port_type, "availability": availability}
    return {"index": index, "name": name, "description": description or name, "mute": False, "volume": volume(100),
            "ports": [port], "active_port": port["name"], "monitor_source": f"{name}.monitor", **extra}


class ParseTest(unittest.TestCase):
    def test_keeps_plugged_devices_with_short_names(self):
        entries = [
            {**sink(1, "alsa_output.laptop", "Speaker", "availability unknown"), "volume": volume(80, 70)},
            sink(2, "alsa_output.hdmi1", "HDMI", "not available"),
            sink(3, "alsa_output.hdmi3", "HDMI", "available"),
            {**sink(4, "bluez_output.A8_F5", "Headset", "available", description="OpenRun by Shokz"), "mute": True,
             "properties": {"api.bluez5.address": "A8:F5:E1:E4:7D:DA"}},
        ]
        self.assertEqual(
            pactl.parse_devices(SINK, entries, "bluez_output.A8_F5"),
            [
                Device(SINK, 1, "alsa_output.laptop", "Laptop speakers", 75, False),
                Device(SINK, 3, "alsa_output.hdmi3", "Monitor", 100, False),
                Device(SINK, 4, "bluez_output.A8_F5", "OpenRun by Shokz", 100, True, default=True, mac="A8:F5:E1:E4:7D:DA"),
            ],
        )

        # Two screens get the port added
        two_screens = [sink(1, "hdmi1", "HDMI", "available"), sink(2, "hdmi2", "HDMI", "available")]
        labels = [d.label for d in pactl.parse_devices(SINK, two_screens, "")]
        self.assertEqual(labels, ["Monitor (HDMI Output 1)", "Monitor (HDMI Output 2)"])

    def test_monitor_sources_are_not_microphones(self):
        sources = [
            {"index": 3, "name": "speakers.monitor", "monitor_source": "speakers", "volume": volume(100)},
            {"index": 4, "name": "mic", "description": "Digital Microphone", "monitor_source": "", "volume": volume(40)},
        ]
        self.assertEqual([d.label for d in pactl.parse_devices(SOURCE, sources, "")], ["Digital Microphone"])


class CommandTest(unittest.TestCase):
    def test_changes_name_the_right_pactl_command(self):
        speakers = Device(SINK, 1, "speakers", "Laptop speakers", 50, False)
        mic = Device(SOURCE, 5, "mic", "Mic", 50, False)
        with patch("outils.pactl.run") as run:
            pactl.set_volume(speakers, 55)
            pactl.set_mute(mic, True)
        self.assertEqual(
            [call.args for call in run.call_args_list],
            [("set-sink-volume", "1", "55%"), ("set-source-mute", "5", "1")],
        )

    def test_using_a_device_moves_what_plays_on_it_but_not_monitor_recordings(self):
        speakers = Device(SINK, 1, "speakers", "Laptop speakers", 50, False)
        mic = Device(SOURCE, 5, "mic", "Mic", 50, False)
        listings = {
            "sink-inputs": [{"index": 7, "sink": 2}, {"index": 8, "sink": 3}],
            "sources": [{"index": 9, "monitor_source": "hdmi"}, {"index": 4, "monitor_source": ""}],
            "source-outputs": [{"index": 11, "source": 4}, {"index": 12, "source": 9}],
        }
        with patch("outils.pactl.run") as run, patch("outils.pactl._json", side_effect=lambda _, what: listings[what]):
            run.side_effect = lambda *args: (_ for _ in ()).throw(PactlError("gone")) if args[1] == "8" else ""
            pactl.set_default(speakers)
            pactl.set_default(mic)
        self.assertEqual(
            [call.args for call in run.call_args_list],
            [
                ("set-default-sink", "speakers"),
                ("move-sink-input", "7", "speakers"),
                ("move-sink-input", "8", "speakers"),
                ("set-default-source", "mic"),
                ("move-source-output", "11", "mic"),
            ],
        )

    def test_failures_become_pactl_errors(self):
        failed = subprocess.CompletedProcess([], 1, "", "Failure: No such entity\n")
        with patch("tui_kit.processes.run", return_value=failed), self.assertRaisesRegex(PactlError, "No such entity"):
            pactl.run("set-sink-mute", "99", "1")
        with patch("tui_kit.processes.run", side_effect=FileNotFoundError), self.assertRaisesRegex(PactlError, "not installed"):
            pactl.run("info")


if __name__ == "__main__":
    unittest.main()
