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

    def test_analyzer_connectivity_and_offline_pf(self):
        import time
        now_ts = int(time.time() * 1000)

        # 1. Online Normal Panel
        p_online = {
            "id": "dev-1",
            "name": "P-1",
            "attributes": {"lastActivityTime": now_ts, "phase": 1, "state": "INSTALLED"},
            "telemetry": {"rv": 230.0, "ri": 10.0, "rly": 1, "pkt": 0}
        }
        res_online = self.analyzer.analyze_single_panel(p_online)
        self.assertTrue(res_online["is_online"])
        self.assertFalse(res_online["is_offline_pf"])
        self.assertFalse(res_online["is_power_failure"])

        # 2. Offline PF via pkt == 8
        p_pkt8 = {
            "id": "dev-2",
            "name": "P-2",
            "attributes": {"lastActivityTime": now_ts, "phase": 1, "state": "INSTALLED"},
            "telemetry": {"rv": 0.0, "ri": 0.0, "rly": 0, "pkt": 8}
        }
        res_pkt8 = self.analyzer.analyze_single_panel(p_pkt8)
        self.assertFalse(res_pkt8["is_online"])
        self.assertTrue(res_pkt8["is_offline_pf"])
        self.assertFalse(res_pkt8["is_power_failure"]) # Section 2 live issue must be False

        # 3. Offline Stale Panel (e.g. 5 hours ago) with 0V: must be Offline PF but NOT Section 2 live PF
        p_stale = {
            "id": "dev-3",
            "name": "P-3",
            "attributes": {"lastActivityTime": now_ts - (5 * 3600 * 1000), "phase": 1, "state": "INSTALLED"},
            "telemetry": {"rv": 0.0, "ri": 0.0, "rly": 0, "pkt": 0}
        }
        res_stale = self.analyzer.analyze_single_panel(p_stale)
        self.assertFalse(res_stale["is_online"])
        self.assertTrue(res_stale["is_offline_pf"])
        self.assertFalse(res_stale["is_power_failure"])

        # 4. Offline Panel (e.g. 5 hours ago) with 150V: must be Offline but NOT Section 2 Low Voltage
        p_stale_low_v = {
            "id": "dev-4",
            "name": "P-4",
            "attributes": {"lastActivityTime": now_ts - (5 * 3600 * 1000), "phase": 1, "state": "INSTALLED"},
            "telemetry": {"rv": 150.0, "ri": 0.0, "rly": 0, "pkt": 0}
        }
        res_stale_lv = self.analyzer.analyze_single_panel(p_stale_low_v)
        self.assertFalse(res_stale_lv["is_online"])
        self.assertTrue(res_stale_lv["is_offline"]) # Must be strictly non-PF offline
        self.assertFalse(res_stale_lv["is_offline_pf"]) # Not power fail
        self.assertFalse(res_stale_lv["is_low_voltage"]) # Section 2 live issue must be False

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
