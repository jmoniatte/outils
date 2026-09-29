import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from outils import rdap
from outils.rdap import RdapError
from outils.web import get_json

ANSWER = {
    "ldhName": "GOOGLE.FR",
    "events": [
        {"eventAction": "registration", "eventDate": "2000-07-26T22:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2026-12-30T17:16:48Z"},
    ],
    "nameservers": [{"ldhName": f"ns{n}.google.com."} for n in range(1, 5)],
    "entities": [
        {"roles": ["registrar", "sponsor"], "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "MARKMONITOR Inc."]]]},
        {"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Google Ireland Holdings"]]]},
    ],
}


class RdapTest(unittest.TestCase):
    def test_rows_give_the_registration_in_order_and_whole_name_servers_that_fit(self):
        self.assertEqual(
            rdap.rows(ANSWER),
            [
                ("Domain", "google.fr"),
                ("Registrar", "MARKMONITOR Inc."),
                ("Registrant", "Google Ireland Holdings"),
                ("Registered", "2000-07-26, expires 2026-12-30"),
                ("Name servers", "ns1.google.com, ns2.google.com, ns3.google.com, +1 more"),
            ],
        )
        # What the registry leaves out is left out
        hidden = {**ANSWER, "entities": ANSWER["entities"][:1]}
        self.assertNotIn("Registrant", [label for label, _ in rdap.rows(hidden)])
        self.assertEqual(rdap.rows({"ldhName": "a.fr", "events": [{"eventAction": "expiration", "eventDate": "2030-01-01T00:00:00Z"}]})[1], ("Registered", "expires 2030-01-01"))
        self.assertEqual(rdap.rows({"ldhName": "a.fr", "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", ""]]]}]}), [("Domain", "a.fr")])

    def test_a_host_is_tried_up_to_its_domain_and_nothing_found_or_a_failure_is_no_rows(self):
        self.assertEqual(rdap.names("www.bbc.co.uk."), ["www.bbc.co.uk", "bbc.co.uk", "co.uk"])
        self.assertEqual(rdap.names("localhost"), [])
        with patch("outils.rdap.get_json", side_effect=[None, ANSWER]) as get:
            self.assertEqual(rdap.lookup("www.google.fr")[0], ("Domain", "google.fr"))
        self.assertEqual([call.args[0] for call in get.call_args_list], ["https://rdap.org/domain/www.google.fr", "https://rdap.org/domain/google.fr"])
        self.assertTrue(get.call_args.kwargs["not_found"])
        with patch("outils.rdap.get_json", return_value=None):
            self.assertEqual(rdap.lookup("nobody.example"), [])
        with patch("outils.rdap.get_json", side_effect=RdapError("Cannot reach rdap.org")):
            self.assertEqual(rdap.lookup("www.google.fr"), [])
        # A name in another script is asked in its ASCII form
        with patch("outils.rdap.get_json", return_value=None) as get:
            rdap.lookup("café.fr")
        self.assertEqual(get.call_args_list[0].args[0], "https://rdap.org/domain/xn--caf-dma.fr")

    def test_a_404_is_none_only_when_asked(self):
        with patch("outils.web.urlopen", side_effect=HTTPError("u", 404, "Not Found", {}, io.BytesIO())):
            self.assertIsNone(get_json("https://rdap.org/domain/a.fr", "rdap.org", RdapError, not_found=True))
            with self.assertRaisesRegex(RdapError, "answered 404"):
                get_json("https://rdap.org/domain/a.fr", "rdap.org", RdapError)


if __name__ == "__main__":
    unittest.main()
