import unittest
from analyzer import PanelAnalyzer
from google_spaces import GoogleSpacesNotifier
from tb_client import ThingsBoardClient
from main import load_config


class TestWardReport(unittest.TestCase):
    def setUp(self):
        self.config = load_config("config.json")
        self.analyzer = PanelAnalyzer(thresholds=self.config.get("alert_thresholds"))
        self.notifier = GoogleSpacesNotifier()

    def test_tb_client_inventory_load(self):
        client = ThingsBoardClient()
        inventory = client.load_ward_devices("ward_devices.json")
        self.assertIn("SNTR-W167", inventory)
        self.assertIn("SVJR-W118", inventory)
        self.assertEqual(len(inventory["SNTR-W167"]), 152)
        self.assertEqual(len(inventory["SVJR-W118"]), 59)

    def test_tb_client_login(self):
        client = ThingsBoardClient()
        logged_in = client.login()
        self.assertTrue(logged_in, "ThingsBoard login should succeed with credentials")

    def test_card_v2_generation(self):
        mock_reports = [
            {
                "zone_name": "Shanthi Nagar (Ward 167)",
                "generated_at": "08-Sep-2026 03:10 PM IST",
                "section1_overview": {
                    "total_panels": 152,
                    "online_panels": 140,
                    "offline_panels": 12,
                    "offline_pf_panels": 4,
                    "online_pct": 92.1,
                },
                "section2_issues": {
                    "low_voltage": 1,
                    "high_voltage": 0,
                    "power_failure": 4,
                    "mcb_trip": 1,
                    "panel_door_open": 2,
                },
            },
            {
                "zone_name": "Shivaji Nagar (Ward 118)",
                "generated_at": "08-Sep-2026 03:10 PM IST",
                "section1_overview": {
                    "total_panels": 57,
                    "online_panels": 54,
                    "offline_panels": 3,
                    "offline_pf_panels": 0,
                    "online_pct": 94.7,
                },
                "section2_issues": {
                    "low_voltage": 0,
                    "high_voltage": 0,
                    "power_failure": 0,
                    "mcb_trip": 0,
                    "panel_door_open": 0,
                },
            },
        ]
        card = self.notifier.build_combined_card_v2(mock_reports)
        self.assertIn("cardsV2", card)
        self.assertEqual(len(card["cardsV2"]), 1)
        sections = card["cardsV2"][0]["card"]["sections"]
        self.assertEqual(len(sections), 3)  # 2 wards + 1 footer
        self.assertIn("92.1% Operational", sections[0]["header"])
        self.assertIn("94.7% Operational", sections[1]["header"])

        md = self.notifier.build_markdown_fallback(mock_reports)
        self.assertIn("BBMP Central Zone", md)
        self.assertIn("Shanthi Nagar (Ward 167)", md)
        self.assertIn("Shivaji Nagar (Ward 118)", md)
        self.assertIn("Issue Breakdown", md)
        self.assertIn("Relay Status", md)
        self.assertIn("Power Failure", md)
        self.assertIn("MCB Trip", md)
        self.assertIn("Panel Door Open", md)


if __name__ == "__main__":
    unittest.main()
