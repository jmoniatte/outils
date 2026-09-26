import subprocess
import unittest
from unittest.mock import patch

from outils import nmcli
from outils.nmcli import Network, NmcliError, Profile, parse_details, parse_profiles, parse_scan, parse_share, saved_list, split_terse

SCAN = r""" :BRETZELS:2452 MHz:100:WPA2
 ::2452 MHz:100:WPA2
 :BRETZELS:5240 MHz:90:WPA2
*:Home\:5G:6295 MHz:60:WPA3
 :Home\:5G:2412 MHz:84:WPA3
 :Cafe:5220 MHz:19:
 :Office:2437 MHz:49:WPA2 802.1X
"""


def network(ssid: str, **fields) -> Network:
    defaults = dict(signal=50, security="WPA2", frequency=2437)
    return Network(ssid=ssid, **{**defaults, **fields})


class ParseTest(unittest.TestCase):
    def test_split_terse_undoes_the_escapes(self):
        self.assertEqual(split_terse(r"*:Home\:5G:a\\b:"), ["*", "Home:5G", r"a\b", ""])
        self.assertEqual(split_terse("one"), ["one"])

    def test_scan_merges_access_points_and_puts_the_one_in_use_first(self):
        networks = parse_scan(SCAN, [Profile("Home:5G", "uuid-home")])
        self.assertEqual([n.ssid for n in networks], ["Home:5G", "BRETZELS", "Office", "Cafe"])

        home, bretzels, office, cafe = networks
        # The access point in use wins over a stronger one with the same SSID
        self.assertEqual((home.in_use, home.signal, home.band), (True, 60, "6 GHz"))
        self.assertEqual((home.saved, home.saved_uuid), (True, "uuid-home"))
        self.assertEqual((bretzels.signal, bretzels.band, bretzels.saved), (100, "2.4 GHz", False))
        self.assertTrue(office.enterprise)
        self.assertEqual((cafe.open, cafe.security, cafe.band), (True, "", "5 GHz"))

    def test_profiles_are_all_listed_the_most_recently_used_first(self):
        output = (
            "connection.uuid:u1\nconnection.timestamp:100\n802-11-wireless.ssid:Home\n\n"
            "connection.uuid:u2\nconnection.timestamp:300\n802-11-wireless.ssid:Cafe\n\n"
            "connection.uuid:u3\nconnection.timestamp:0\n802-11-wireless.ssid:\n\n"
            "connection.uuid:u4\nconnection.timestamp:200\n802-11-wireless.ssid:Home\n"
        )
        self.assertEqual(parse_profiles(output), [Profile("Cafe", "u2"), Profile("Home", "u4"), Profile("Home", "u1")])

    def test_saved_list_puts_profiles_in_range_first_then_the_others_by_name(self):
        profiles = [Profile("Home:5G", "u1"), Profile("zoo", "u2"), Profile("Attic", "u3")]
        saved = saved_list(parse_scan(SCAN, profiles), profiles)
        self.assertEqual([(n.ssid, n.in_range) for n in saved], [("Home:5G", True), ("Attic", False), ("zoo", False)])
        self.assertEqual(saved[2].saved_uuid, "u2")

    def test_two_profiles_for_one_ssid_are_one_nearby_row_and_two_saved_ones(self):
        profiles = [Profile("Home:5G", "recent"), Profile("Home:5G", "older")]
        nearby = parse_scan(SCAN, profiles)
        self.assertEqual((nearby[0].ssid, nearby[0].saved_uuid), ("Home:5G", "recent"))
        saved = saved_list(nearby, profiles)
        self.assertEqual([(n.saved_uuid, n.in_use) for n in saved], [("recent", True), ("older", False)])

    def test_details_combine_the_device_and_the_access_point_in_use(self):
        shown = (
            "GENERAL.CONNECTION:Home\nGENERAL.CON-UUID:u1\nGENERAL.HWADDR:44:F7:9F:82:6E:95\n"
            "IP4.ADDRESS[1]:192.168.0.200/24\nIP4.GATEWAY:192.168.0.1\n"
            "IP4.DNS[1]:1.1.1.3\nIP4.DNS[2]:1.0.0.3\nIP6.ADDRESS[1]:fe80::1/64\nIP6.GATEWAY:\n"
        )
        access_points = (
            r" :AA\:BB:Other:6:2437 MHz:130 Mbit/s:90:WPA2" "\n"
            r"*:82\:22\:54\:32\:55\:F5:Home:69:6295 MHz:0 Mbit/s:67:WPA3" "\n"
        )
        details = parse_details("wlp1s0", shown, access_points)
        self.assertEqual((details.ssid, details.bssid, details.band, details.channel), ("Home", "82:22:54:32:55:F5", "6 GHz", 69))
        self.assertEqual((details.signal, details.rate, details.security), (67, 0, "WPA3"))
        self.assertEqual(details.addresses, ("192.168.0.200/24",))
        self.assertEqual((details.gateway, details.dns, details.ipv6), ("192.168.0.1", ("1.1.1.3", "1.0.0.3"), ("fe80::1/64",)))
        self.assertEqual((details.mac, details.uuid), ("44:F7:9F:82:6E:95", "u1"))
        # Without the access point in the list, the connection name stands in for the SSID
        self.assertEqual(parse_details("wlp1s0", shown, "").ssid, "Home")

    def test_share_reads_the_secrets_with_colons_left_as_they_are(self):
        output = (
            "802-11-wireless.ssid:a:b\n802-11-wireless-security.key-mgmt:sae\n"
            "802-11-wireless-security.psk:p:w\\d\n802-11-wireless-security.wep-key0:\n"
        )
        shared = parse_share(output)
        self.assertEqual((shared.ssid, shared.key_mgmt, shared.password), ("a:b", "sae", "p:w\\d"))
        self.assertEqual(shared.qr_security, "WPA")
        self.assertFalse(shared.enterprise)
        open_network = parse_share("802-11-wireless.ssid:Cafe\n802-11-wireless-security.key-mgmt:\n")
        self.assertEqual((open_network.password, open_network.qr_security), ("", None))
        self.assertEqual(parse_share("802-11-wireless-security.key-mgmt:none\n802-11-wireless-security.wep-key0:k\n").password, "k")
        self.assertTrue(parse_share("802-11-wireless-security.key-mgmt:wpa-eap\n").enterprise)


class ConnectTest(unittest.TestCase):
    def test_password_goes_on_stdin_and_never_in_the_arguments(self):
        with patch("outils.nmcli.run", return_value="") as run:
            nmcli.connect(network("Cafe"), "s3cret")
        args, kwargs = run.call_args
        self.assertEqual(kwargs["stdin"], "s3cret\n")
        self.assertNotIn("s3cret", args)
        self.assertIn("--ask", args)
        self.assertEqual(args[-4:], ("device", "wifi", "connect", "Cafe"))

    def test_saved_network_comes_up_through_its_profile(self):
        with patch("outils.nmcli.run", return_value="") as run:
            nmcli.connect(network("Home", saved_uuid="u1"))
        self.assertEqual(run.call_args.args[-4:], ("connection", "up", "uuid", "u1"))

    def test_a_failed_connect_deletes_the_profile_it_created(self):
        calls = []

        def run(*args, **kwargs):
            calls.append(args)
            if "connect" in args:
                raise NmcliError("Secrets were required, but not provided")
            return ""

        with patch("outils.nmcli.run", side_effect=run), patch("outils.nmcli.saved_networks", side_effect=[[], [Profile("Cafe", "new")]]):
            with self.assertRaisesRegex(NmcliError, "Secrets"):
                nmcli.connect(network("Cafe"), "wrong")
        self.assertEqual(calls[-1], ("connection", "delete", "uuid", "new"))

        # A profile saved before the attempt, which a stale list did not show, keeps its password
        calls.clear()
        with patch("outils.nmcli.run", side_effect=run), patch("outils.nmcli.saved_networks", return_value=[Profile("Cafe", "old")]):
            with self.assertRaisesRegex(NmcliError, "Secrets"):
                nmcli.connect(network("Cafe"), "wrong")
        self.assertNotIn("delete", [arg for args in calls for arg in args])

    def test_radio_and_connectivity_calls(self):
        with patch("outils.nmcli.run", return_value="portal\n") as run:
            self.assertEqual(nmcli.connectivity(), "portal")
            self.assertEqual(run.call_args.args, ("-t", "networking", "connectivity"))
            nmcli.set_wifi(False)
            self.assertEqual(run.call_args.args, ("radio", "wifi", "off"))

    def test_disconnect_takes_down_the_active_wifi_connection_only(self):
        active = "Wired:w1:802-3-ethernet\nHome:u1:802-11-wireless\n"
        with patch("outils.nmcli.run", side_effect=[active, ""]) as run:
            self.assertEqual(nmcli.disconnect(), "Home")
        self.assertEqual(run.call_args.args, ("connection", "down", "uuid", "u1"))
        with patch("outils.nmcli.run", return_value="Wired:w1:802-3-ethernet\n"):
            self.assertEqual(nmcli.disconnect(), "")

    def test_errors_carry_the_last_line_nmcli_printed(self):
        failed = subprocess.CompletedProcess([], 10, "", "Warning: something\nError: No network with SSID 'x' found.\n")
        with patch("tui_kit.processes.run", return_value=failed):
            with self.assertRaisesRegex(NmcliError, "^No network with SSID 'x' found.$"):
                nmcli.run("device", "wifi", "connect", "x")
        with patch("tui_kit.processes.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(NmcliError, "not installed"):
                nmcli.run("radio", "wifi")


if __name__ == "__main__":
    unittest.main()
